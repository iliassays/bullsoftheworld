"""Bounded bootstrap of legacy current-state data into the immutable observation ledger.

This command intentionally does not infer historical publication times. Existing bars are stamped
``legacy_unknown`` and become eligible only for research cutoffs after the bootstrap time. Run it
in small resumable slices on a constrained host::

    uv run python -m ingestion.foundation_bootstrap US --limit 25
    uv run python -m ingestion.foundation_bootstrap US --after AAPL --limit 25
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys

from sqlalchemy import distinct, select

from bulls.core.db import get_sessionmaker
from bulls.core.models import DailyBar
from ingestion.lineage import record_daily_bar_observations


async def bootstrap_daily_bars(
    market: str,
    *,
    after: str | None = None,
    limit: int = 25,
    pause_ms: int = 100,
) -> dict[str, int | str | None]:
    """Seed immutable bar revisions one symbol/transaction at a time."""
    market = market.upper()
    if limit <= 0:
        raise ValueError("limit must be positive")
    sm = get_sessionmaker()
    async with sm() as session:
        statement = select(distinct(DailyBar.code)).where(DailyBar.market == market)
        if after:
            statement = statement.where(DailyBar.code > after.upper())
        codes = list(await session.scalars(statement.order_by(DailyBar.code).limit(limit)))

    observed_at = dt.datetime.now(dt.UTC)
    observations = 0
    bars_seen = 0
    for code in codes:
        async with sm() as session:
            bars = list(
                await session.scalars(
                    select(DailyBar)
                    .where(DailyBar.market == market, DailyBar.code == code)
                    .order_by(DailyBar.date)
                )
            )
            bars_seen += len(bars)
            observations += await record_daily_bar_observations(
                session,
                bars,
                observed_at=observed_at,
                knowledge_time_quality="legacy_unknown",
            )
            await session.commit()
        if pause_ms:
            await asyncio.sleep(pause_ms / 1000)
    return {
        "market": market,
        "symbols": len(codes),
        "bars_seen": bars_seen,
        "observations_inserted": observations,
        "next_after": codes[-1] if codes else after,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap immutable research observations")
    parser.add_argument("market", choices=("DSE", "US"))
    parser.add_argument("--after", help="resume after this symbol (exclusive)")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--pause-ms", type=int, default=100)
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args(sys.argv[1:])
    stats = asyncio.run(
        bootstrap_daily_bars(
            args.market,
            after=args.after,
            limit=args.limit,
            pause_ms=args.pause_ms,
        )
    )
    print(stats)


if __name__ == "__main__":
    main()
