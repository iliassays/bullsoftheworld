"""Market-wide EOD summary collection for DSE (index levels, turnover, breadth).

Same shape as history.py but market-level: one ranged call to market_summary.php, not per-symbol.
dsebd serves the same rolling ~2-year window here, so we backfill once then append daily — our
table keeps history past what dsebd will re-serve.

    uv run python -m ingestion.market_summary backfill   # one-time, ~2 years
    uv run python -m ingestion.market_summary daily       # incremental, recent window (cron this)
"""

from __future__ import annotations

import asyncio
import datetime as dt
import sys

from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.db import get_sessionmaker
from bulls.core.models import MarketSummary
from bulls.market_data import get_provider

BACKFILL_DAYS = 760  # over 2y; the endpoint caps at ~474 rows anyway
DAILY_LOOKBACK_DAYS = 10  # re-pull a short window daily to catch late corrections


async def _upsert(session, summaries) -> int:
    if not summaries:
        return 0
    rows = [s.model_dump() for s in summaries]
    stmt = pg_insert(MarketSummary).values(rows)
    update_cols = {c: getattr(stmt.excluded, c) for c in rows[0] if c not in ("market", "date")}
    stmt = stmt.on_conflict_do_update(index_elements=["market", "date"], set_=update_cols)
    await session.execute(stmt)
    return len(rows)


async def collect(market: str, *, days: int) -> dict[str, int]:
    """Pull `days` of market summaries and upsert. Returns run stats."""
    provider = get_provider(market)
    end = dt.datetime.now(dt.UTC).date()
    start = end - dt.timedelta(days=days)
    summaries = await provider.get_market_summary(start, end)
    sm = get_sessionmaker()
    async with sm() as session:
        n = await _upsert(session, summaries)
        await session.commit()
    return {"days_upserted": n}


async def _run(market: str, mode: str) -> None:
    days = BACKFILL_DAYS if mode == "backfill" else DAILY_LOOKBACK_DAYS
    print(f"[summary] {mode}: pulling ~{days}d of {market} market summary")
    stats = await collect(market, days=days)
    print(f"[summary] done: {stats}")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    asyncio.run(_run("DSE", mode))


if __name__ == "__main__":
    main()
