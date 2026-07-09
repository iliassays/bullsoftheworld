"""Historical daily-bar collection.

dsebd.org's day-end archive only serves ~the last 2 years (474 trading days) per symbol — there's
no deeper history through it. So we:
  1. backfill that ~2-year window for every instrument once, then
  2. append the latest bars daily — our daily_bars table grows past what dsebd will ever serve.

    uv run python -m ingestion.history backfill   # one-time, all symbols, ~2 years
    uv run python -m ingestion.history daily       # incremental, recent window (cron this)
    uv run python -m ingestion.history US backfill --years 10 --limit 100

Requests are slow and public providers are fragile, so we use modest concurrency + per-symbol
retries and skip failures rather than aborting the whole run.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import sys
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.db import get_sessionmaker
from bulls.core.models import DailyBar, Symbol
from bulls.market_data import get_provider

BACKFILL_DAYS = 760  # a bit over 2y; the endpoint caps at ~474 rows anyway
DAILY_LOOKBACK_DAYS = 10  # re-pull a short window daily to catch late corrections
US_BACKFILL_DAYS = 3653  # 10y including leap days; enough for long-cycle drawdown/factor context
US_DAILY_LOOKBACK_DAYS = 14
CONCURRENCY = 4
RETRIES = 3

BACKFILL_DAYS_BY_MARKET = {"DSE": BACKFILL_DAYS, "US": US_BACKFILL_DAYS}
DAILY_LOOKBACK_DAYS_BY_MARKET = {"DSE": DAILY_LOOKBACK_DAYS, "US": US_DAILY_LOOKBACK_DAYS}


async def _upsert_bars(session, bars) -> int:
    if not bars:
        return 0
    rows = [b.model_dump() for b in bars]
    stmt = pg_insert(DailyBar).values(rows)
    update_cols = {
        c: getattr(stmt.excluded, c) for c in rows[0] if c not in ("market", "code", "date")
    }
    stmt = stmt.on_conflict_do_update(index_elements=["market", "code", "date"], set_=update_cols)
    await session.execute(stmt)
    return len(rows)


async def _collect_symbol(provider, code: str, start: dt.date, end: dt.date) -> int:
    last_err: Exception | None = None
    for _ in range(RETRIES):
        try:
            bars = await provider.get_daily_bars(code, start, end)
            sm = get_sessionmaker()
            async with sm() as session:
                n = await _upsert_bars(session, bars)
                await session.commit()
            return n
        except Exception as e:
            last_err = e
            await asyncio.sleep(2)
    print(f"  ! {code}: giving up after {RETRIES} tries ({last_err})")
    return 0


async def _active_codes_from_db(market: str) -> list[str]:
    sm = get_sessionmaker()
    async with sm() as session:
        rows = list(
            await session.scalars(
                select(Symbol.code)
                .where(
                    Symbol.market == market,
                    Symbol.is_active.is_(True),
                    Symbol.is_hidden.is_(False),
                )
                .order_by(Symbol.code)
            )
        )
    return rows


async def _symbol_codes(market: str, provider) -> list[str]:
    codes = await _active_codes_from_db(market)
    if codes:
        return codes
    symbols = await provider.list_symbols()
    return sorted(s.code for s in symbols)


def _select_codes(
    codes: list[str],
    *,
    wanted: Iterable[str] | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> list[str]:
    selected = codes
    if wanted:
        wanted_set = {c.strip().upper() for c in wanted if c.strip()}
        selected = [c for c in selected if c in wanted_set]
    if offset:
        selected = selected[offset:]
    if limit is not None:
        selected = selected[:limit]
    return selected


async def collect(
    market: str,
    *,
    days: int,
    concurrency: int = CONCURRENCY,
    codes: Iterable[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, int]:
    """Pull `days` of daily bars for every instrument and upsert. Returns run stats."""
    market = market.upper()
    provider = get_provider(market)
    all_codes = await _symbol_codes(market, provider)
    selected_codes = _select_codes(all_codes, wanted=codes, offset=offset, limit=limit)
    end = dt.datetime.now(dt.UTC).date()
    start = end - dt.timedelta(days=days)

    sem = asyncio.Semaphore(concurrency)
    done = 0
    total = len(selected_codes)

    async def one(code: str) -> int:
        nonlocal done
        async with sem:
            n = await _collect_symbol(provider, code, start, end)
            done += 1
            if done % 25 == 0 or done == total:
                print(f"  ...{done}/{total} symbols")
            return n

    counts = await asyncio.gather(*(one(code) for code in selected_codes))
    return {
        "symbols_available": len(all_codes),
        "symbols": total,
        "symbols_with_data": sum(1 for c in counts if c),
        "bars_upserted": sum(counts),
    }


def _mode_market(first: str | None, second: str | None) -> tuple[str, str]:
    known_markets = {"DSE", "US"}
    if first and first.upper() in known_markets:
        return first.upper(), second or "daily"
    return (second or os.getenv("MARKET") or "DSE").upper(), first or "daily"


def _default_days(market: str, mode: str) -> int:
    if mode == "backfill":
        return BACKFILL_DAYS_BY_MARKET.get(market, BACKFILL_DAYS)
    return DAILY_LOOKBACK_DAYS_BY_MARKET.get(market, DAILY_LOOKBACK_DAYS)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect historical daily bars.")
    parser.add_argument("first", nargs="?", help="mode or market, e.g. backfill or US")
    parser.add_argument("second", nargs="?", help="market or mode, e.g. US or backfill")
    parser.add_argument("--days", type=int, help="calendar days to request")
    parser.add_argument("--years", type=float, help="calendar years to request")
    parser.add_argument("--limit", type=int, help="maximum symbols to process")
    parser.add_argument("--offset", type=int, default=0, help="stable offset into active symbols")
    parser.add_argument("--codes", help="comma-separated symbol codes to process")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY)
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args(sys.argv[1:])
    market, mode = _mode_market(args.first, args.second)
    if mode not in {"daily", "backfill"}:
        raise SystemExit("mode must be 'daily' or 'backfill'")
    if args.days is not None and args.years is not None:
        raise SystemExit("use --days or --years, not both")
    days = (
        args.days
        if args.days is not None
        else round(args.years * 365.25)
        if args.years is not None
        else _default_days(market, mode)
    )
    codes = [c.strip() for c in args.codes.split(",")] if args.codes else None
    scope = f"codes={','.join(codes)}" if codes else f"offset={args.offset} limit={args.limit or 'all'}"
    print(
        f"[history] {market} {mode}: pulling ~{days}d daily bars "
        f"(concurrency={args.concurrency}, {scope})"
    )
    stats = asyncio.run(
        collect(
            market,
            days=days,
            concurrency=args.concurrency,
            codes=codes,
            limit=args.limit,
            offset=args.offset,
        )
    )
    print(f"[history] done: {stats}")


if __name__ == "__main__":
    main()
