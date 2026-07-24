"""FINRA bi-monthly consolidated short interest ingestion.

Source: FINRA's public `otcMarket/consolidatedShortInterest` dataset. `settlementDate` is a
partition key, so the API requires an EQUAL filter on it — which is exactly the shape we want:
one settlement date per request, idempotent per date.

This ingests the *open short position*, unlike `finra_short.py` which ingests daily short-marked
*volume*. Only this dataset supports short-interest, %-of-shares and days-to-cover language.

Point-in-time: `known_at` is settlement + `DISSEMINATION_BUSINESS_DAYS` US trading days, computed
identically for backfill and live runs so results are reproducible. See the model docstring.

One-shot:
    uv run python -m ingestion.finra_short_interest              # recent settlement dates
    uv run python -m ingestion.finra_short_interest 2026-06-30   # one settlement date
    uv run python -m ingestion.finra_short_interest --backfill 24
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import io
import logging
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.db import get_sessionmaker
from bulls.core.models import (
    DISSEMINATION_BUSINESS_DAYS,
    SecurityMaster,
    ShortInterestBiweekly,
    Symbol,
)
from bulls.market_data.calendar import is_trading_day
from bulls.market_data.providers.us_security_master import PRODUCT_INSTRUMENT_TYPES
from ingestion.finra_short import _build_symbol_aliases

log = logging.getLogger(__name__)

MARKET = "US"
_URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
_UA = "Mozilla/5.0 BullsOfTheWorld/0.1 finra-short-interest"
_PAGE = 5000
_MAX_PAGES = 40  # ~22k rows per settlement date today; 200k ceiling is ample headroom
_BATCH = 1000
_RECENT_SETTLEMENTS = 4


def dissemination_known_at(
    settlement: dt.date, *, business_days: int = DISSEMINATION_BUSINESS_DAYS
) -> dt.datetime:
    """Conservative UTC knowledge timestamp for one settlement date.

    Walks forward over US trading days. Returns end-of-day so a same-day research cutoff never
    counts a record as known before its dissemination session closed.
    """

    day = settlement
    remaining = business_days
    while remaining > 0:
        day += dt.timedelta(days=1)
        if is_trading_day(day, market=MARKET):
            remaining -= 1
    return dt.datetime.combine(day, dt.time.max, tzinfo=dt.UTC)


def settlement_dates(reference: dt.date, count: int) -> list[dt.date]:
    """The `count` most recent FINRA settlement dates on or before `reference`, oldest first.

    FINRA reports as of the 15th and the last day of each month; when that lands on a non-trading
    day the effective settlement rolls back to the prior trading day.
    """

    def adjust(day: dt.date) -> dt.date:
        while not is_trading_day(day, market=MARKET):
            day -= dt.timedelta(days=1)
        return day

    out: list[dt.date] = []
    year, month = reference.year, reference.month
    while len(out) < count:
        last_day = (dt.date(year, month, 28) + dt.timedelta(days=4)).replace(
            day=1
        ) - dt.timedelta(days=1)
        for candidate in (adjust(last_day), adjust(dt.date(year, month, 15))):
            if candidate <= reference and candidate not in out:
                out.append(candidate)
            if len(out) >= count:
                break
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return sorted(out)


def _number(record: dict, field: str) -> Decimal | None:
    """Decimal value for one CSV field, or None when absent/unparseable."""

    raw = (record.get(field) or "").strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def parse_rows(payload: str, *, expected: dt.date) -> list[dict]:
    """Parse one settlement date's CSV payload; skip rows we cannot trust."""

    reader = csv.DictReader(io.StringIO(payload))
    rows: list[dict] = []
    for record in reader:
        symbol = (record.get("symbolCode") or "").strip()
        raw_settlement = (record.get("settlementDate") or "").strip()
        if not symbol or not raw_settlement:
            continue
        try:
            settlement = dt.date.fromisoformat(raw_settlement)
        except ValueError:
            continue
        if settlement != expected:
            continue

        shares_short = _number(record, "currentShortPositionQuantity")
        if shares_short is None or shares_short < 0:
            continue
        rows.append(
            {
                "symbol": symbol,
                "settlement_date": settlement,
                "shares_short": shares_short,
                "previous_shares_short": _number(record, "previousShortPositionQuantity"),
                "average_daily_volume": _number(record, "averageDailyVolumeQuantity"),
                "days_to_cover": _number(record, "daysToCoverQuantity"),
                "change_pct": _number(record, "changePercent"),
                "market_class": (record.get("marketClassCode") or "").strip()[:16] or None,
            }
        )
    return rows


async def _fetch_settlement(client: httpx.AsyncClient, settlement: dt.date) -> list[dict]:
    """Page through one settlement date. Empty list means FINRA has not published it yet."""

    collected: list[dict] = []
    for page in range(_MAX_PAGES):
        response = await client.post(
            _URL,
            json={
                "limit": _PAGE,
                "offset": page * _PAGE,
                "compareFilters": [
                    {
                        "fieldName": "settlementDate",
                        "fieldValue": settlement.isoformat(),
                        "compareType": "EQUAL",
                    }
                ],
            },
        )
        if response.status_code in {403, 404}:
            return []
        response.raise_for_status()
        text = response.text.strip()
        if not text:
            break
        rows = parse_rows(text, expected=settlement)
        collected.extend(rows)
        # A short page is the last page; the API echoes a header row on every page.
        if len(text.splitlines()) <= _PAGE:
            break
    return collected


async def collect(
    target: dt.date | None = None, *, backfill: int = 0, force: bool = False
) -> dict[str, int]:
    """Ingest one settlement date, the recent window, or `backfill` historical dates."""

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        known = set(await session.scalars(select(Symbol.code).where(Symbol.market == MARKET)))
        securities = list(
            await session.scalars(
                select(SecurityMaster).where(
                    SecurityMaster.market == MARKET,
                    SecurityMaster.is_active.is_(True),
                    SecurityMaster.symbol.in_(known),
                    SecurityMaster.instrument_type.in_(PRODUCT_INSTRUMENT_TYPES),
                )
            )
        )
        aliases = _build_symbol_aliases(securities, known)
        stored = set(
            await session.scalars(
                select(ShortInterestBiweekly.settlement_date)
                .where(ShortInterestBiweekly.market == MARKET)
                .distinct()
            )
        )

    today = dt.datetime.now(dt.UTC).date()
    if target is not None:
        dates = [target]
    else:
        wanted = settlement_dates(today, backfill or _RECENT_SETTLEMENTS)
        dates = [value for value in wanted if force or value not in stored]

    stats = {
        "dates_fetched": 0,
        "dates_pending": 0,
        "rows_upserted": 0,
        "rows_unknown_symbol": 0,
    }
    if not dates:
        return stats

    async with httpx.AsyncClient(
        headers={"User-Agent": _UA, "Content-Type": "application/json"},
        timeout=120,
        follow_redirects=True,
    ) as client:
        for settlement in dates:
            rows = await _fetch_settlement(client, settlement)
            if not rows:
                # Not yet disseminated — routine for a recent settlement date, never an error.
                stats["dates_pending"] += 1
                continue
            known_at = dissemination_known_at(settlement)
            payloads: list[dict] = []
            for row in rows:
                code = aliases.get(row["symbol"]) or aliases.get(row["symbol"].replace("/", "."))
                if code is None:
                    stats["rows_unknown_symbol"] += 1
                    continue
                payloads.append(
                    {
                        "market": MARKET,
                        "code": code,
                        "settlement_date": row["settlement_date"],
                        "known_at": known_at,
                        "shares_short": row["shares_short"],
                        "previous_shares_short": row["previous_shares_short"],
                        "average_daily_volume": row["average_daily_volume"],
                        "days_to_cover": row["days_to_cover"],
                        "change_pct": row["change_pct"],
                        "market_class": row["market_class"],
                        "source": "finra_consolidated",
                    }
                )
            async with sessionmaker() as session:
                for start in range(0, len(payloads), _BATCH):
                    chunk = payloads[start : start + _BATCH]
                    statement = pg_insert(ShortInterestBiweekly).values(chunk)
                    await session.execute(
                        statement.on_conflict_do_update(
                            index_elements=["market", "code", "settlement_date"],
                            set_={
                                column: getattr(statement.excluded, column)
                                for column in (
                                    "known_at",
                                    "shares_short",
                                    "previous_shares_short",
                                    "average_daily_volume",
                                    "days_to_cover",
                                    "change_pct",
                                    "market_class",
                                    "source",
                                )
                            },
                        )
                    )
                    stats["rows_upserted"] += len(chunk)
                await session.commit()
            stats["dates_fetched"] += 1
            log.info(
                "finra_short_interest settlement=%s rows=%s known_at=%s",
                settlement,
                len(payloads),
                known_at.date(),
            )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest FINRA consolidated short interest")
    parser.add_argument("settlement", nargs="?", help="one settlement date (YYYY-MM-DD)")
    parser.add_argument("--backfill", type=int, default=0, help="most recent N settlement dates")
    parser.add_argument("--force", action="store_true", help="re-fetch dates already stored")
    arguments = parser.parse_args()
    target = dt.date.fromisoformat(arguments.settlement) if arguments.settlement else None
    stats = asyncio.run(collect(target, backfill=arguments.backfill, force=arguments.force))
    print(
        f"[finra-short-interest] dates={stats['dates_fetched']} "
        f"pending={stats['dates_pending']} rows={stats['rows_upserted']} "
        f"unknown_symbol={stats['rows_unknown_symbol']}"
    )


if __name__ == "__main__":
    main()
