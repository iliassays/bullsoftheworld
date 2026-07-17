"""Advance the complete private US research catalog within a protected runtime budget."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
from pathlib import Path
from typing import Any

from ingestion.universe_onboarding_batch import run_batch
from ingestion.universe_onboarding_nightly import (
    MIN_RUN_SECONDS,
    in_protected_window,
    runtime_budget_seconds,
)

DEFAULT_CATALOG_DIR = Path("var/us-full-universe")


def latest_catalog_index(catalog_dir: Path) -> Path | None:
    candidates = sorted(
        (path for path in catalog_dir.glob("*/manifest-index.json") if path.is_file()),
        key=lambda path: path.parent.name,
    )
    return candidates[-1] if candidates else None


async def advance_catalog(
    index_path: Path,
    *,
    now: dt.datetime,
    run_batch_fn=run_batch,
) -> dict[str, Any]:
    if in_protected_window(now):
        return {"status": "protected_window", "index": str(index_path), "cohorts": []}
    budget = runtime_budget_seconds(now)
    if budget < MIN_RUN_SECONDS:
        return {
            "status": "insufficient_window",
            "index": str(index_path),
            "budget_seconds": budget,
            "cohorts": [],
        }

    started = dt.datetime.now(dt.UTC)
    outcomes: list[dict[str, Any]] = []
    status = "budget_exhausted"
    while True:
        elapsed = (dt.datetime.now(dt.UTC) - started).total_seconds()
        if elapsed + MIN_RUN_SECONDS > budget:
            break
        result = await run_batch_fn(
            index_path,
            max_cohorts=1,
            fetch=True,
            continue_on_failure=True,
            refresh_security_master=False,
        )
        outcomes.append(result)
        if result["failed"]:
            status = "cohort_failed"
            break
        if result["requested_cohorts"] == 0:
            status = "complete"
            break
    return {
        "status": status,
        "index": str(index_path),
        "budget_seconds": budget,
        "elapsed_seconds": round((dt.datetime.now(dt.UTC) - started).total_seconds(), 3),
        "cohorts": outcomes,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Advance complete US private research onboarding")
    parser.add_argument("--index", type=Path)
    parser.add_argument("--catalog-dir", type=Path, default=DEFAULT_CATALOG_DIR)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    index = args.index or latest_catalog_index(args.catalog_dir)
    if index is None:
        print(json.dumps({"status": "no_catalog", "catalog_dir": str(args.catalog_dir)}))
        return
    result = asyncio.run(advance_catalog(index, now=dt.datetime.now(dt.UTC)))
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
