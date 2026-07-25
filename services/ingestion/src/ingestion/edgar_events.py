"""EDGAR filing-event poller: daily index -> immutable archive -> parsed event tables.

Stage 0.1 of the institutional-study roadmap. The contract, in order of importance:

1. **Archive first.** Every fetched byte (the daily index and each filing) is written to
   the immutable object store before any parsing; ``edgar_filing_events`` records the
   object key + sha256. Replay from the archive is byte-identical to the live fetch.
2. **Parse second, fail soft.** A filing that will not parse is recorded as
   ``parse_status='failed'`` and never blocks the rest of the day.
3. **Append-only.** Accessions already captured are skipped; nothing is updated in place.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import logging
import sys
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.config import get_settings
from bulls.core.db import get_sessionmaker
from bulls.core.models import EdgarFilingEvent, InsiderTransaction, OwnershipStakeEvent
from bulls.market_data.providers.sec_13dg import parse_13dg
from bulls.market_data.providers.sec_daily_index import (
    DailyIndexEntry,
    SecDailyIndexClient,
    parse_acceptance_datetime,
)
from bulls.market_data.providers.sec_form4 import parse_form4

logger = logging.getLogger(__name__)

# The event streams the research needs (institutional study, Phase 12 System A).
# EDGAR's daily-index form label for Schedule 13D/G changed from "SC 13D"/"SC 13G"
# to "SCHEDULE 13D"/"SCHEDULE 13G" (confirmed live: the last "SC 13D/A" appears
# 2024-12-31, "SCHEDULE 13D/A" already alongside it that day, and exclusively from
# 2025-01-02 on) -- both spellings are kept so historical and current data both match.
TARGET_FORMS = frozenset(
    {
        "4",
        "4/A",
        "SC 13D",
        "SC 13D/A",
        "SC 13G",
        "SC 13G/A",
        "SCHEDULE 13D",
        "SCHEDULE 13D/A",
        "SCHEDULE 13G",
        "SCHEDULE 13G/A",
    }
)

_MAX_FILING_BYTES = 50 * 1024 * 1024

# A Section 16 transaction is reportable within two business days, so it cannot happen after the
# filing that reports it. The tolerance absorbs timezone skew between the filer's local
# transaction date and EDGAR's index date; anything beyond it is a filer typo (production held
# transaction dates out to 2033). Such a date is nulled, never repaired — the intended digits
# are unknowable, and the rest of the row (owner, code, shares, price) is still true.
_FILED_DATE_TOLERANCE = dt.timedelta(days=1)


def _user_agent() -> str:
    settings = get_settings()
    return f"BullsOfTheWorld/1.0 {settings.sec_contact_email}"


def index_object_key(day: dt.date) -> str:
    return f"edgar/daily-index/{day:%Y/%m/%d}/master.idx"


def filing_object_key(accession_number: str) -> str:
    return f"edgar/filings/{accession_number}.txt"


@dataclass
class ParsedFiling:
    """Parse outcome for one captured filing; rows are ready-to-insert dicts."""

    parse_status: str
    insider_rows: list[dict] = field(default_factory=list)
    stake_row: dict | None = None
    # EDGAR acceptance timestamp, read form-agnostically from the SGML header. This is the
    # point-in-time anchor every filings signal is stamped with (institutional study 13.1.1),
    # so it must be captured for Form 4 exactly as it is for 13D/G.
    accepted_at: dt.datetime | None = None
    # Transaction dates nulled as unusable — the parser's floor plus dates the filing date
    # disproves. Surfaced so the rate is observable instead of silently absorbed.
    implausible_dates: int = 0


def _plausible_transaction_date(
    transaction_date: dt.date | None, filed_date: dt.date | None
) -> dt.date | None:
    """Drop a transaction date the filing date proves impossible. The floor is the parser's."""
    if transaction_date is None or filed_date is None:
        return transaction_date
    if transaction_date > filed_date + _FILED_DATE_TOLERANCE:
        return None
    return transaction_date


def parse_filing(entry: DailyIndexEntry, raw: bytes) -> ParsedFiling:
    """Route a raw dissemination file to the right parser. Pure function."""
    accepted_at = parse_acceptance_datetime(raw)
    if entry.form in {"4", "4/A"}:
        filing = parse_form4(raw)
        if filing is None:
            return ParsedFiling(parse_status="failed", accepted_at=accepted_at)
        rows = []
        # Dates the parser already rejected against its floor, plus the ones the filing date
        # disproves below — so the counter means "unusable transaction dates", full stop.
        implausible = filing.implausible_transaction_dates
        for owner in filing.owners:
            for row_index, txn in enumerate(filing.transactions):
                transaction_date = _plausible_transaction_date(
                    txn.transaction_date, entry.date_filed
                )
                if transaction_date is None and txn.transaction_date is not None:
                    implausible += 1
                rows.append(
                    {
                        "accession_number": entry.accession_number,
                        "row_index": row_index,
                        "issuer_cik": filing.issuer_cik,
                        "issuer_symbol": filing.issuer_symbol,
                        "issuer_name": filing.issuer_name,
                        "owner_cik": owner.cik,
                        "owner_name": owner.name,
                        "is_director": owner.is_director,
                        "is_officer": owner.is_officer,
                        "is_ten_percent_owner": owner.is_ten_percent_owner,
                        "officer_title": owner.officer_title,
                        "is_10b5_1_plan": filing.is_10b5_1_plan,
                        "security_title": txn.security_title,
                        "transaction_date": transaction_date,
                        "code": txn.code,
                        "shares": txn.shares,
                        "price_per_share": txn.price_per_share,
                        "acquired_disposed": txn.acquired_disposed,
                        "shares_owned_after": txn.shares_owned_after,
                        "direct_or_indirect": txn.direct_or_indirect,
                        "has_derivative_transactions": filing.has_derivative_transactions,
                    }
                )
        return ParsedFiling(
            parse_status="parsed",
            insider_rows=rows,
            accepted_at=accepted_at,
            implausible_dates=implausible,
        )

    stake = parse_13dg(raw)
    if stake is None:
        return ParsedFiling(parse_status="failed", accepted_at=accepted_at)
    return ParsedFiling(
        parse_status="parsed",
        accepted_at=stake.accepted_at or accepted_at,
        stake_row={
            "accession_number": stake.accession_number,
            "form": stake.form,
            "subject_cik": stake.subject_cik,
            "subject_name": stake.subject_name,
            "filed_by_cik": stake.filed_by_cik,
            "filed_by_name": stake.filed_by_name,
            "filed_date": stake.filed_date,
            "accepted_at": stake.accepted_at,
            "percent_of_class": stake.percent_of_class,
        },
    )


def plan_new_entries(entries: list[DailyIndexEntry], existing: set[str]) -> list[DailyIndexEntry]:
    """Keep target-form entries whose accession is new. Pure function.

    The daily index lists one row per filer CIK, so a single Form 4 (issuer +
    each reporting owner) or a jointly-filed 13D routinely appears more than
    once under the same accession number. Dedupe within the batch too, or
    every such filing gets fetched from SEC twice and ``collect_day``'s
    counts overstate unique filings by the same factor.
    """
    planned: list[DailyIndexEntry] = []
    seen: set[str] = set()
    for entry in entries:
        accession = entry.accession_number
        if entry.form not in TARGET_FORMS or accession is None or accession in existing:
            continue
        if accession in seen:
            continue
        seen.add(accession)
        planned.append(entry)
    return planned


async def _existing_accessions(session, accessions: list[str]) -> set[str]:
    if not accessions:
        return set()
    result = await session.execute(
        select(EdgarFilingEvent.accession_number).where(
            EdgarFilingEvent.accession_number.in_(accessions)
        )
    )
    return {row[0] for row in result}


async def collect_day(
    day: dt.date,
    *,
    store,
    client: SecDailyIndexClient | None = None,
) -> dict[str, int]:
    """Capture one day's target filings: archive, parse, persist. Idempotent."""
    client = client or SecDailyIndexClient(user_agent=_user_agent())
    counts = {
        "index_entries": 0,
        "captured": 0,
        "parsed": 0,
        "failed": 0,
        "skipped": 0,
        "implausible_dates": 0,
    }

    raw_index, entries = await client.fetch_day(day, forms=set(TARGET_FORMS))
    if raw_index is None:
        return counts  # weekend/holiday: a normal empty day, not an error
    counts["index_entries"] = len(entries)
    store.put(
        key=index_object_key(day),
        payload=raw_index,
        content_type="text/plain",
    )

    sm = get_sessionmaker()
    async with sm() as session:
        known = await _existing_accessions(
            session, [e.accession_number for e in entries if e.accession_number]
        )
        planned = plan_new_entries(entries, known)

        for entry in planned:
            accession = entry.accession_number
            raw = await client.fetch_filing(entry.filename)
            if raw is None or len(raw) > _MAX_FILING_BYTES:
                counts["skipped"] += 1
                continue
            stored = store.put(
                key=filing_object_key(accession),
                payload=raw,
                content_type="text/plain",
            )
            outcome = parse_filing(entry, raw)
            counts["captured"] += 1
            counts["parsed" if outcome.parse_status == "parsed" else "failed"] += 1
            counts["implausible_dates"] += outcome.implausible_dates

            await session.execute(
                pg_insert(EdgarFilingEvent)
                .values(
                    accession_number=accession,
                    market="US",
                    form=entry.form,
                    cik=entry.cik,
                    company_name=entry.company,
                    filed_date=entry.date_filed,
                    accepted_at=outcome.accepted_at,
                    index_filename=entry.filename,
                    raw_object_key=stored.key,
                    raw_sha256=stored.sha256,
                    parse_status=outcome.parse_status,
                )
                .on_conflict_do_nothing(index_elements=["accession_number"])
            )
            if outcome.insider_rows:
                await session.execute(
                    pg_insert(InsiderTransaction)
                    .values(outcome.insider_rows)
                    .on_conflict_do_nothing(constraint="uq_insider_transactions_row")
                )
            if outcome.stake_row is not None:
                await session.execute(
                    pg_insert(OwnershipStakeEvent)
                    .values(outcome.stake_row)
                    .on_conflict_do_nothing(index_elements=["accession_number"])
                )
        await session.commit()
    return counts


def replay_day_index(day: dt.date, *, store) -> bytes:
    """Read the archived daily index back, byte-identical to the original fetch."""
    return store.get(key=index_object_key(day), max_bytes=_MAX_FILING_BYTES)


def replay_filing(accession_number: str, *, store) -> bytes:
    """Read an archived filing back, byte-identical to the original fetch."""
    return store.get(key=filing_object_key(accession_number), max_bytes=_MAX_FILING_BYTES)


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture EDGAR filing events for one day")
    parser.add_argument("--day", type=dt.date.fromisoformat, default=None)
    return parser.parse_args(argv)


def main() -> None:
    from ingestion.us_options.storage import object_store

    args = _args()
    day = args.day or (dt.datetime.now(dt.UTC).date() - dt.timedelta(days=1))
    counts = asyncio.run(collect_day(day, store=object_store()))
    json.dump({"day": day.isoformat(), **counts}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
