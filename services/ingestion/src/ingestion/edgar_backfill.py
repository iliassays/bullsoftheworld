"""One-off historical backfill for the EDGAR filing-event stream.

Loops ``edgar_events.collect_day`` over a date range, oldest day first. Unlike the
daily cron, this is meant to run once (or be re-run to fill a gap) against a long
range, so it must survive a bad day without losing the rest of the run: each day's
outcome is caught and logged, never allowed to abort the whole backfill.

Usage: ``uv run python -m ingestion.edgar_backfill --start 2024-07-01 --end 2026-07-19``
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import logging
import sys

from ingestion.edgar_events import collect_day
from ingestion.us_options.storage import object_store

logger = logging.getLogger(__name__)


def _dates(start: dt.date, end: dt.date):
    if end < start:
        raise ValueError(f"end {end} is before start {start}")
    day = start
    while day <= end:
        yield day
        day += dt.timedelta(days=1)


async def run_backfill(start: dt.date, end: dt.date) -> dict[str, int]:
    """Capture every day in [start, end]. Returns the summed counts."""
    store = object_store()
    totals = {"days": 0, "index_entries": 0, "captured": 0, "parsed": 0, "failed": 0, "skipped": 0}
    for day in _dates(start, end):
        try:
            counts = await collect_day(day, store=store)
        except Exception:
            logger.exception("edgar_backfill_day_failed day=%s", day)
            continue
        totals["days"] += 1
        for key, value in counts.items():
            totals[key] += value
        logger.info("edgar_backfill_day_complete day=%s counts=%s totals=%s", day, counts, totals)
        print(json.dumps({"day": day.isoformat(), **counts}), flush=True)
    return totals


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill EDGAR filing events over a date range")
    parser.add_argument("--start", type=dt.date.fromisoformat, required=True)
    parser.add_argument("--end", type=dt.date.fromisoformat, default=None)
    return parser.parse_args(argv)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _args()
    end = args.end or (dt.datetime.now(dt.UTC).date() - dt.timedelta(days=1))
    totals = asyncio.run(run_backfill(args.start, end))
    json.dump({"start": args.start.isoformat(), "end": end.isoformat(), **totals}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
