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


async def bootstrap_all_daily_bars(
    market: str,
    *,
    after: str | None = None,
    batch_size: int = 25,
    pause_ms: int = 100,
) -> dict[str, int | str | None]:
    """Run every bounded slice, preserving an explicit cursor after each committed batch."""
    cursor = after
    symbols = 0
    bars_seen = 0
    observations = 0
    while True:
        batch = await bootstrap_daily_bars(
            market,
            after=cursor,
            limit=batch_size,
            pause_ms=pause_ms,
        )
        count = int(batch["symbols"])
        symbols += count
        bars_seen += int(batch["bars_seen"])
        observations += int(batch["observations_inserted"])
        if count == 0:
            break
        cursor = str(batch["next_after"])
        print(
            f"[foundation-bootstrap] market={market} symbols={symbols} "
            f"bars={bars_seen} inserted={observations} next_after={cursor}",
            flush=True,
        )
        if count < batch_size:
            break
    return {
        "market": market.upper(),
        "symbols": symbols,
        "bars_seen": bars_seen,
        "observations_inserted": observations,
        "next_after": cursor,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap immutable research observations")
    parser.add_argument("market", choices=("DSE", "US"))
    parser.add_argument("--after", help="resume after this symbol (exclusive)")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--pause-ms", type=int, default=100)
    parser.add_argument("--all", action="store_true", help="continue until every symbol is done")
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args(sys.argv[1:])
    operation = bootstrap_all_daily_bars if args.all else bootstrap_daily_bars
    kwargs = {
        "after": args.after,
        "pause_ms": args.pause_ms,
        ("batch_size" if args.all else "limit"): args.limit,
    }
    stats = asyncio.run(operation(args.market, **kwargs))
    print(stats)


if __name__ == "__main__":
    main()
