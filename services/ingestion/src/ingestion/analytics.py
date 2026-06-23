"""Compute the analytics snapshot for every symbol and persist it.

Runs after the EOD bar pull (in the scheduler), so the screener/dashboard reads a fresh
ticker_analytics row per symbol with plain SQL instead of recomputing on each request.

One-shot (cron-friendly / backfill now):
    uv run python -m ingestion.analytics DSE
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.analytics import compute
from bulls.core.db import get_sessionmaker
from bulls.core.models import DailyBar, Symbol, TickerAnalytics

_LOOKBACK = 260  # enough for the 200-day SMA
_FIELDS = (
    "last_close",
    "sma_50",
    "sma_200",
    "above_sma_50",
    "above_sma_200",
    "rsi_14",
    "atr_14",
    "nearest_support",
    "nearest_resistance",
    "week52_high",
    "week52_low",
    "pct_from_52w_high",
    "pct_from_52w_low",
    "avg_volume_20",
    "relative_volume",
    "cmf_20",
)


async def compute_all(market: str) -> dict[str, int]:
    """Compute + upsert analytics for every symbol with price history. Returns counts."""
    sm = get_sessionmaker()
    async with sm() as session:
        codes = list(await session.scalars(select(Symbol.code).where(Symbol.market == market)))

    computed = 0
    async with sm() as session:
        for code in codes:
            bars = list(
                await session.scalars(
                    select(DailyBar)
                    .where(DailyBar.market == market, DailyBar.code == code)
                    .order_by(DailyBar.date.desc())
                    .limit(_LOOKBACK)
                )
            )
            if not bars:
                continue
            result = compute(list(reversed(bars)))
            row = {"market": market, "code": code, "as_of_date": result.as_of_date}
            row.update({f: getattr(result, f) for f in _FIELDS})

            stmt = pg_insert(TickerAnalytics).values(row)
            update_cols = {c: getattr(stmt.excluded, c) for c in row if c not in ("market", "code")}
            stmt = stmt.on_conflict_do_update(index_elements=["market", "code"], set_=update_cols)
            await session.execute(stmt)
            computed += 1
        await session.commit()

    return {"symbols": len(codes), "computed": computed}


async def _run(market: str) -> None:
    counts = await compute_all(market)
    print(f"[analytics] {market}: computed {counts['computed']}/{counts['symbols']} symbols")


def main() -> None:
    market = sys.argv[1] if len(sys.argv) > 1 else "DSE"
    asyncio.run(_run(market))


if __name__ == "__main__":
    main()
