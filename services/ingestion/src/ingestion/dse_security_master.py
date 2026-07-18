"""Forward-only DSE listing identity and eligibility lineage.

The public DSE instrument list cannot recreate historical membership. This adapter starts an
effective-dated control plane from the first accepted deployment without pretending to backfill
the past. Snapshot quality is checked before an absent symbol can be recorded as removed.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import exists, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.models import SecurityListingObservation, SecurityMaster, Symbol
from bulls.market_data import Symbol as ProviderSymbol
from ingestion.lineage import (
    content_sha256,
    persist_source_snapshot,
    record_security_listing_events,
)

DSE_SECURITY_MASTER_NORMALIZATION_VERSION = "dse-security-master-v1"
MINIMUM_LIVE_RECORDS = 300
MINIMUM_PRIOR_COVERAGE_RATIO = 0.85


@dataclass(frozen=True, slots=True)
class DseListingSnapshotQuality:
    records: int
    prior_active_records: int
    coverage_ratio: float | None


def validate_dse_listing_snapshot(
    records: list[ProviderSymbol],
    *,
    previous_active_count: int = 0,
) -> DseListingSnapshotQuality:
    """Reject empty, duplicate, cross-market, or sharply truncated instrument snapshots."""

    if not records:
        raise ValueError("DSE listing snapshot is empty")
    if any(record.market != "DSE" for record in records):
        raise ValueError("DSE listing snapshot contains a non-DSE record")
    duplicates = sorted(
        code for code, count in Counter(record.code for record in records).items() if count > 1
    )
    if duplicates:
        raise ValueError(
            "DSE listing snapshot contains duplicate symbols: " + ", ".join(duplicates[:5])
        )
    if len(records) < MINIMUM_LIVE_RECORDS:
        raise ValueError(
            f"DSE listing snapshot is incomplete: {len(records)} < {MINIMUM_LIVE_RECORDS} records"
        )
    coverage_ratio = len(records) / previous_active_count if previous_active_count > 0 else None
    if coverage_ratio is not None and coverage_ratio < MINIMUM_PRIOR_COVERAGE_RATIO:
        raise ValueError(
            "DSE listing coverage collapsed: "
            f"{len(records)}/{previous_active_count} ({coverage_ratio:.1%})"
        )
    return DseListingSnapshotQuality(
        records=len(records),
        prior_active_records=previous_active_count,
        coverage_ratio=coverage_ratio,
    )


def _normalized_record(record: ProviderSymbol) -> dict:
    return {
        "market": "DSE",
        "symbol": record.code,
        "security_name": record.name_en,
        "sector": record.sector,
        "category": record.category,
        "exchange": "DSE",
        "instrument_type": "listed_instrument",
        "is_active": True,
        "is_product_eligible": True,
    }


def _master_row(record: ProviderSymbol, observed_at: dt.datetime) -> dict:
    return {
        "market": "DSE",
        "symbol": record.code,
        "raw_symbol": record.code,
        "security_name": record.name_en,
        "exchange": "DSE",
        "exchange_tier": record.category,
        "cqs_symbol": None,
        "nasdaq_symbol": None,
        "cik": None,
        "instrument_type": "listed_instrument",
        "is_etf": False,
        "is_test_issue": False,
        "is_active": True,
        "is_product_eligible": True,
        "exclude_reason": None,
        "round_lot_size": None,
        "financial_status": record.category,
        "source": "dse_scrape",
        "source_file": "dse_instruments",
        "last_seen_at": observed_at,
        "updated_at": observed_at,
    }


def _listing_payload(record: SecurityMaster, *, is_active: bool | None = None) -> dict:
    return {
        "market": record.market,
        "symbol": record.symbol,
        "security_name": record.security_name,
        "exchange": record.exchange,
        "cik": record.cik,
        "instrument_type": record.instrument_type,
        "is_active": record.is_active if is_active is None else is_active,
        "is_product_eligible": (record.is_product_eligible if is_active is None else is_active),
        "exclude_reason": record.exclude_reason if is_active is None else "not_seen",
    }


async def persist_dse_listing_snapshot(
    session,
    records: list[ProviderSymbol],
    *,
    observed_at: dt.datetime,
) -> dict[str, int]:
    """Persist one accepted DSE listing delivery and only its changed identity events."""

    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("DSE listing observed_at must be timezone-aware")

    existing_rows = list(
        await session.scalars(select(SecurityMaster).where(SecurityMaster.market == "DSE"))
    )
    existing = {row.symbol: row for row in existing_rows}
    existing_payloads = {row.symbol: _listing_payload(row) for row in existing_rows}
    existing_active = {row.symbol: row.is_active for row in existing_rows}
    prior_active = sum(row.is_active for row in existing_rows)
    quality = validate_dse_listing_snapshot(
        records,
        previous_active_count=prior_active,
    )
    normalized = [
        _normalized_record(record) for record in sorted(records, key=lambda item: item.code)
    ]
    snapshot_id = await persist_source_snapshot(
        session,
        market="DSE",
        dataset_key="security_master",
        provider="dse_instruments",
        # Listing state can legitimately return to an earlier content hash after a removal and
        # relisting. A delivery-specific scope preserves that later event instead of resolving to
        # the older manifest whose observation rows are already unique by source snapshot.
        scope_key=f"listed_universe:{observed_at.isoformat()}",
        normalized_records=normalized,
        normalization_version=DSE_SECURITY_MASTER_NORMALIZATION_VERSION,
        known_at=observed_at,
        effective_at=observed_at,
        quality_report={
            "records": quality.records,
            "previous_active_records": quality.prior_active_records,
            "coverage_ratio": quality.coverage_ratio,
        },
        source_metadata={"raw_archive_available": False},
    )

    rows = [_master_row(record, observed_at) for record in records]
    statement = pg_insert(SecurityMaster).values(rows)
    update_columns = {
        column: getattr(statement.excluded, column)
        for column in rows[0]
        if column not in {"market", "symbol", "first_seen_at", "security_id"}
    }
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["market", "symbol"],
            set_=update_columns,
        )
    )
    persisted_rows = list(
        await session.scalars(
            select(SecurityMaster)
            .where(SecurityMaster.market == "DSE")
            .execution_options(populate_existing=True)
        )
    )
    persisted = {row.symbol: row for row in persisted_rows}
    history_exists = bool(
        await session.scalar(select(exists().where(SecurityListingObservation.market == "DSE")))
    )
    incoming = {record.code for record in records}
    events: list[dict] = []
    for code in sorted(incoming):
        current = persisted[code]
        payload = _listing_payload(current)
        previous = existing.get(code)
        previous_payload = existing_payloads.get(code)
        if (
            history_exists
            and previous is not None
            and content_sha256(payload) == content_sha256(previous_payload)
        ):
            continue
        events.append(
            {
                "source_snapshot_id": snapshot_id,
                "security_id": current.security_id,
                "event_kind": (
                    "added"
                    if previous is None or not history_exists or not existing_active[code]
                    else "updated"
                ),
                **payload,
                "known_at": observed_at,
                "row_sha256": content_sha256(payload),
            }
        )
    for previous in existing_rows:
        if not previous.is_active or previous.symbol in incoming:
            continue
        payload = _listing_payload(previous, is_active=False)
        events.append(
            {
                "source_snapshot_id": snapshot_id,
                "security_id": previous.security_id,
                "event_kind": "removed",
                **payload,
                "known_at": observed_at,
                "row_sha256": content_sha256(payload),
            }
        )
    inserted_events = await record_security_listing_events(session, events)
    await session.execute(
        update(SecurityMaster)
        .where(
            SecurityMaster.market == "DSE",
            SecurityMaster.symbol.not_in(incoming),
            SecurityMaster.is_active.is_(True),
        )
        .values(
            is_active=False,
            is_product_eligible=False,
            exclude_reason="not_seen",
            updated_at=observed_at,
        )
    )
    await session.execute(
        update(Symbol)
        .where(
            Symbol.market == "DSE",
            SecurityMaster.market == Symbol.market,
            SecurityMaster.symbol == Symbol.code,
            Symbol.security_id.is_distinct_from(SecurityMaster.security_id),
        )
        .values(security_id=SecurityMaster.security_id)
    )
    return {
        "records": len(records),
        "events": inserted_events,
        "removed": sum(event["event_kind"] == "removed" for event in events),
    }
