"""Historical daily-bar collection for DSE.

dsebd.org's day-end archive only serves ~the last 2 years (474 trading days) per symbol — there's
no deeper history through it. So we:
  1. backfill that ~2-year window for every instrument once, then
  2. append the latest bars daily — our daily_bars table grows past what dsebd will ever serve.

    uv run python -m ingestion.history backfill   # one-time, all symbols, ~2 years
    uv run python -m ingestion.history daily       # incremental, recent window (cron this)

Requests are slow and dsebd is fragile, so we use modest concurrency + per-symbol retries and skip
failures rather than aborting the whole run.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import sys

from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.db import get_sessionmaker
from bulls.core.models import DailyBar
from bulls.market_data import get_provider

BACKFILL_DAYS = 760  # a bit over 2y; the endpoint caps at ~474 rows anyway
DAILY_LOOKBACK_DAYS = 10  # re-pull a short window daily to catch late corrections
CONCURRENCY = 4
RETRIES = 3


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


async def collect(market: str, *, days: int, concurrency: int = CONCURRENCY) -> dict[str, int]:
    """Pull `days` of daily bars for every instrument and upsert. Returns run stats."""
    provider = get_provider(market)
    symbols = await provider.list_symbols()
    end = dt.datetime.now(dt.UTC).date()
    start = end - dt.timedelta(days=days)

    sem = asyncio.Semaphore(concurrency)
    done = 0
    total = len(symbols)

    async def one(code: str) -> int:
        nonlocal done
        async with sem:
            n = await _collect_symbol(provider, code, start, end)
            done += 1
            if done % 25 == 0 or done == total:
                print(f"  ...{done}/{total} symbols")
            return n

    counts = await asyncio.gather(*(one(s.code) for s in symbols))
    return {
        "symbols": total,
        "symbols_with_data": sum(1 for c in counts if c),
        "bars_upserted": sum(counts),
    }


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    days = BACKFILL_DAYS if mode == "backfill" else DAILY_LOOKBACK_DAYS
    print(f"[history] {mode}: pulling ~{days}d of DSE daily bars")
    stats = asyncio.run(collect("DSE", days=days))
    print(f"[history] done: {stats}")


if __name__ == "__main__":
    main()
