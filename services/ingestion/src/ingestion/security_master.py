"""US security-master onboarding.

This is intentionally separate from price ingestion. The job first builds a raw, auditable security
master, then publishes only eligible instruments into the product-facing `symbols` table. That keeps
warrants, rights, units, preferreds, test issues, and deficient listings out of retail discovery
without losing provenance.

    uv run python -m ingestion.security_master US
"""

from __future__ import annotations

import asyncio
import datetime as dt
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import case, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.config import get_settings
from bulls.core.db import get_sessionmaker
from bulls.core.models import SecurityListingObservation, SecurityMaster, Symbol
from bulls.market_data.providers.us_security_master import (
    UsSecurityRecord,
    fetch_us_security_master,
)
from ingestion.lineage import (
    SECURITY_MASTER_NORMALIZATION_VERSION,
    content_sha256,
    persist_source_snapshot,
    record_security_listing_events,
)

UPSERT_BATCH_SIZE = 1000
MINIMUM_LIVE_RECORDS = 1_000
MINIMUM_RECORDS_PER_LISTING_FILE = 500
MINIMUM_PRIOR_COVERAGE_RATIO = 0.75
MINIMUM_CIK_COVERAGE_RATIO = 0.70


@dataclass(frozen=True, slots=True)
class SecurityMasterSnapshotQuality:
    records: int
    active_records: int
    eligible_records: int
    cik_eligible_records: int
    cik_coverage_ratio: float
    records_by_source_file: dict[str, int]


def validate_security_master_snapshot(
    records: list[UsSecurityRecord],
    *,
    previous_active_count: int = 0,
) -> SecurityMasterSnapshotQuality:
    """Reject incomplete listing snapshots before they can deactivate the current universe.

    All three upstream downloads complete before this function runs, but a syntactically valid
    truncated listing file is still dangerous: persistence treats unseen rows as inactive. The
    absolute, per-file, duplicate, prior-coverage, and CIK checks make that destructive transition
    fail closed. Thresholds are deliberately loose enough for normal listing churn.
    """
    if not records:
        raise ValueError("US security-master snapshot is empty")
    if any(record.market != "US" for record in records):
        raise ValueError("US security-master snapshot contains a non-US record")

    duplicate_symbols = [
        symbol
        for symbol, count in Counter(record.symbol for record in records).items()
        if count > 1
    ]
    if duplicate_symbols:
        sample = ", ".join(sorted(duplicate_symbols)[:5])
        raise ValueError(f"US security-master snapshot contains duplicate symbols: {sample}")

    by_source = Counter(record.source_file for record in records)
    for source_file in ("nasdaqlisted", "otherlisted"):
        count = by_source.get(source_file, 0)
        if count < MINIMUM_RECORDS_PER_LISTING_FILE:
            raise ValueError(
                f"US security-master {source_file} snapshot is incomplete: "
                f"{count} < {MINIMUM_RECORDS_PER_LISTING_FILE} records"
            )

    active = sum(record.is_active for record in records)
    minimum_expected = max(
        MINIMUM_LIVE_RECORDS,
        round(previous_active_count * MINIMUM_PRIOR_COVERAGE_RATIO),
    )
    if active < minimum_expected:
        raise ValueError(
            "US security-master active coverage collapsed: "
            f"{active} < {minimum_expected} (previous={previous_active_count})"
        )

    eligible = [record for record in records if record.is_product_eligible]
    cik_candidates = [
        record for record in eligible if record.instrument_type in {"common_stock", "adr"}
    ]
    with_cik = sum(record.cik is not None for record in cik_candidates)
    cik_ratio = with_cik / len(cik_candidates) if cik_candidates else 0.0
    if not cik_candidates or cik_ratio < MINIMUM_CIK_COVERAGE_RATIO:
        raise ValueError(
            "US security-master SEC identity coverage is incomplete: "
            f"{with_cik}/{len(cik_candidates)} ({cik_ratio:.1%})"
        )

    return SecurityMasterSnapshotQuality(
        records=len(records),
        active_records=active,
        eligible_records=len(eligible),
        cik_eligible_records=with_cik,
        cik_coverage_ratio=cik_ratio,
        records_by_source_file=dict(sorted(by_source.items())),
    )


def _user_agent() -> str:
    settings = get_settings()
    contact = settings.sec_contact_email
    return f"BullsOfTheWorld/0.1 security-master {contact}"


def _security_rows(records: list[UsSecurityRecord], fetched_at: dt.datetime) -> list[dict]:
    return [
        {
            **record.model_dump(),
            "last_seen_at": fetched_at,
            "updated_at": fetched_at,
        }
        for record in records
    ]


def _listing_payload(record) -> dict:
    """Canonical identity/product state; volatile collection timestamps are excluded."""
    return {
        "market": record.market,
        "symbol": record.symbol,
        "security_name": record.security_name,
        "exchange": record.exchange,
        "cik": record.cik,
        "instrument_type": record.instrument_type,
        "is_active": record.is_active,
        "is_product_eligible": record.is_product_eligible,
        "exclude_reason": record.exclude_reason,
    }


def identity_continuity_conflicts(
    existing: Mapping[str, SecurityMaster], records: list[UsSecurityRecord]
) -> list[str]:
    """Detect symbol reuse before an upsert can rewrite the stable listing identity.

    A CIK transfer can be legitimate, but it is never safe to accept silently because all
    historical bars currently key by symbol. The operator must resolve that event explicitly.
    """
    conflicts: list[str] = []
    for record in records:
        previous = existing.get(record.symbol)
        if (
            previous is not None
            and previous.cik is not None
            and record.cik is not None
            and previous.cik != record.cik
        ):
            conflicts.append(f"{record.symbol}:{previous.cik}->{record.cik}")
    return sorted(conflicts)


def _symbol_rows(records: list[UsSecurityRecord]) -> list[dict]:
    return [
        {
            "market": record.market,
            "code": record.symbol,
            "name_en": record.security_name,
            "name_bn": None,
            "sector": None,
            "category": None,
            "is_active": True,
            "is_hidden": False,
            "data_status": "reference_only",
            "research_status": "reference_only",
        }
        for record in records
        if record.is_product_eligible
    ]


def _chunks[T](rows: list[T], size: int = UPSERT_BATCH_SIZE) -> list[list[T]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


async def _upsert_security_master(session, rows: list[dict]) -> None:
    for batch in _chunks(rows):
        stmt = pg_insert(SecurityMaster).values(batch)
        update_cols = {
            col: getattr(stmt.excluded, col)
            for col in batch[0]
            if col not in {"market", "symbol", "first_seen_at"}
        }
        stmt = stmt.on_conflict_do_update(index_elements=["market", "symbol"], set_=update_cols)
        await session.execute(stmt)


async def _upsert_product_symbols(session, rows: list[dict]) -> None:
    for batch in _chunks(rows):
        stmt = pg_insert(Symbol).values(batch)
        update_cols = {
            "name_en": stmt.excluded.name_en,
            "name_bn": stmt.excluded.name_bn,
            "sector": stmt.excluded.sector,
            "category": stmt.excluded.category,
            "is_active": stmt.excluded.is_active,
        }
        stmt = stmt.on_conflict_do_update(index_elements=["market", "code"], set_=update_cols)
        await session.execute(stmt)


def security_id_backlink_stmt(market: str):
    """Join-style backlink update touching only rows whose security_id actually changes.

    A correlated-subquery form rewrote every symbol row per run (with FK checks and index
    churn on each), which exceeded the 30s statement timeout on a loaded host.
    """
    return (
        update(Symbol)
        .where(
            Symbol.market == market,
            SecurityMaster.market == Symbol.market,
            SecurityMaster.symbol == Symbol.code,
            Symbol.security_id.is_distinct_from(SecurityMaster.security_id),
        )
        .values(security_id=SecurityMaster.security_id)
    )


async def persist_security_master(records: list[UsSecurityRecord]) -> dict[str, int]:
    fetched_at = dt.datetime.now(dt.UTC)
    security_rows = _security_rows(records, fetched_at)
    symbol_rows = _symbol_rows(records)

    sm = get_sessionmaker()
    async with sm() as session:
        market = records[0].market if records else "US"
        existing_rows = list(
            await session.scalars(select(SecurityMaster).where(SecurityMaster.market == market))
        )
        existing = {row.symbol: row for row in existing_rows}
        conflicts = identity_continuity_conflicts(existing, records)
        if conflicts:
            sample = ", ".join(conflicts[:5])
            raise ValueError(
                "US security-master identity continuity check failed; "
                f"manual symbol-reuse review required: {sample}"
            )
        normalized_records = [
            record.model_dump(mode="json") for record in sorted(records, key=lambda row: row.symbol)
        ]
        snapshot_id = await persist_source_snapshot(
            session,
            market=market,
            dataset_key="security_master",
            provider="nasdaq_trader_sec",
            scope_key="listed_universe",
            normalized_records=normalized_records,
            normalization_version=SECURITY_MASTER_NORMALIZATION_VERSION,
            known_at=fetched_at,
            effective_at=fetched_at,
            source_metadata={
                "raw_archive_available": False,
                "source_files": dict(Counter(row.source_file for row in records)),
            },
        )
        history_exists = bool(
            await session.scalar(
                select(exists().where(SecurityListingObservation.market == market))
            )
        )
        await _upsert_security_master(session, security_rows)
        await _upsert_product_symbols(session, symbol_rows)
        if records:
            await session.execute(security_id_backlink_stmt(market))
            persisted_rows = list(
                await session.scalars(select(SecurityMaster).where(SecurityMaster.market == market))
            )
            persisted = {row.symbol: row for row in persisted_rows}
            events: list[dict] = []
            incoming_symbols = {record.symbol for record in records}
            for record in records:
                current = persisted[record.symbol]
                payload = _listing_payload(current)
                previous = existing.get(record.symbol)
                previous_payload = _listing_payload(previous) if previous is not None else None
                if not history_exists or previous is None:
                    event_kind = "added"
                elif content_sha256(payload) != content_sha256(previous_payload):
                    event_kind = "updated"
                else:
                    continue
                events.append(
                    {
                        "source_snapshot_id": snapshot_id,
                        "security_id": current.security_id,
                        "event_kind": event_kind,
                        **payload,
                        "known_at": fetched_at,
                        "row_sha256": content_sha256(payload),
                    }
                )
            for previous in existing_rows:
                if not previous.is_active or previous.symbol in incoming_symbols:
                    continue
                payload = {**_listing_payload(previous), "is_active": False}
                events.append(
                    {
                        "source_snapshot_id": snapshot_id,
                        "security_id": previous.security_id,
                        "event_kind": "removed",
                        **payload,
                        "known_at": fetched_at,
                        "row_sha256": content_sha256(payload),
                    }
                )
            await record_security_listing_events(session, events)
            await session.execute(
                update(SecurityMaster)
                .where(SecurityMaster.market == market, SecurityMaster.last_seen_at < fetched_at)
                .values(is_active=False, is_product_eligible=False, exclude_reason="not_seen")
            )
            await session.execute(
                update(Symbol)
                .where(
                    Symbol.market == market,
                    exists().where(
                        SecurityMaster.market == Symbol.market,
                        SecurityMaster.symbol == Symbol.code,
                        SecurityMaster.is_active.is_(True),
                        SecurityMaster.is_product_eligible.is_(False),
                    ),
                )
                .values(
                    is_hidden=case(
                        (Symbol.data_status == "research_only", False),
                        else_=True,
                    ),
                    data_status=case(
                        (Symbol.data_status == "ready", "degraded"),
                        else_=Symbol.data_status,
                    ),
                    research_status=case(
                        (Symbol.research_status.in_(("ready", "partial")), "degraded"),
                        else_=Symbol.research_status,
                    ),
                    research_status_updated_at=fetched_at,
                )
            )
            await session.execute(
                update(Symbol)
                .where(
                    Symbol.market == market,
                    ~exists().where(
                        SecurityMaster.market == Symbol.market,
                        SecurityMaster.symbol == Symbol.code,
                        SecurityMaster.is_active.is_(True),
                    ),
                )
                .values(
                    is_active=False,
                    research_status="unavailable",
                    research_status_updated_at=fetched_at,
                )
            )
        await session.commit()

    return {
        "raw_securities": len(records),
        "product_symbols": len(symbol_rows),
        "common_stocks": sum(1 for r in records if r.instrument_type == "common_stock"),
        "adrs": sum(1 for r in records if r.instrument_type == "adr"),
        "etfs": sum(1 for r in records if r.instrument_type == "etf"),
        "excluded": sum(1 for r in records if not r.is_product_eligible),
        "with_cik": sum(1 for r in records if r.cik is not None),
    }


async def _active_security_count(market: str) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(SecurityMaster)
                .where(
                    SecurityMaster.market == market,
                    SecurityMaster.is_active.is_(True),
                )
            )
            or 0
        )


async def collect(market: str = "US") -> dict[str, int]:
    if market.upper() != "US":
        raise ValueError("security_master currently supports market='US' only")
    records = await fetch_us_security_master(_user_agent())
    quality = validate_security_master_snapshot(
        records,
        previous_active_count=await _active_security_count("US"),
    )
    stats = await persist_security_master(records)
    return {
        **stats,
        "active_records": quality.active_records,
        "cik_eligible_records": quality.cik_eligible_records,
    }


def main() -> None:
    market = sys.argv[1] if len(sys.argv) > 1 else "US"
    print(f"[security-master] refreshing {market} listed universe")
    stats = asyncio.run(collect(market))
    print(f"[security-master] done: {stats}")


if __name__ == "__main__":
    main()
