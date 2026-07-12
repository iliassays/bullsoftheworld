"""Run generated US onboarding cohorts sequentially with explicit bounds and safe resume behavior."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select

from bulls.core.db import get_sessionmaker
from bulls.core.models import UniverseOnboardingRun
from ingestion.cohorts import CohortManifest, load_cohort
from ingestion.universe_onboarding import run_onboarding


def selected_cohort_files(
    index_path: Path,
    *,
    band: str | None,
    max_cohorts: int | None,
) -> list[tuple[Path, str]]:
    payload = json.loads(index_path.read_text())
    if payload.get("market") != "US" or not isinstance(payload.get("cohorts"), list):
        raise ValueError("manifest index must contain a US cohorts list")
    selected: list[tuple[Path, str]] = []
    for item in payload["cohorts"]:
        if not isinstance(item, dict):
            continue
        item_band = str(item.get("band") or "")
        if band and item_band != band:
            continue
        filename = str(item.get("file") or "")
        path = (index_path.parent / filename).resolve()
        if path.parent != index_path.parent.resolve():
            raise ValueError(f"cohort file escapes manifest directory: {filename}")
        selected.append((path, str(item.get("manifest_sha256") or "")))
        if max_cohorts is not None and len(selected) >= max_cohorts:
            break
    return selected


async def _already_completed(manifest: CohortManifest) -> bool:
    sm = get_sessionmaker()
    async with sm() as session:
        completed = await session.scalar(
            select(UniverseOnboardingRun.id)
            .where(
                UniverseOnboardingRun.market == manifest.market,
                UniverseOnboardingRun.manifest_sha256 == manifest.manifest_sha256,
                UniverseOnboardingRun.status == "completed",
                UniverseOnboardingRun.promotion_requested.is_(False),
            )
            .limit(1)
        )
    return completed is not None


async def run_batch(
    index_path: Path,
    *,
    band: str | None = None,
    max_cohorts: int | None = 1,
    fetch: bool = True,
    rerun_completed: bool = False,
    continue_on_failure: bool = False,
) -> dict[str, Any]:
    files = selected_cohort_files(index_path, band=band, max_cohorts=max_cohorts)
    summary: dict[str, Any] = {"requested_cohorts": len(files), "completed": [], "skipped": [], "failed": []}
    for path, expected_hash in files:
        manifest = load_cohort(path, "US")
        if expected_hash and manifest.manifest_sha256 != expected_hash:
            raise ValueError(f"manifest hash mismatch: {path.name}")
        if not rerun_completed and await _already_completed(manifest):
            summary["skipped"].append({"file": path.name, "reason": "already_completed"})
            continue
        try:
            result = await run_onboarding(manifest, fetch=fetch, promote=False)
            summary["completed"].append({"file": path.name, **result})
        except Exception as error:
            summary["failed"].append(
                {"file": path.name, "error": f"{type(error).__name__}: {error}"}
            )
            if not continue_on_failure:
                raise
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage generated US cohorts sequentially")
    parser.add_argument("index", type=Path, help="generated manifest-index.json")
    parser.add_argument(
        "--band",
        choices=("mid_cap", "small_cap", "micro_cap", "nano_cap", "ultra_nano_cap"),
    )
    parser.add_argument("--max-cohorts", type=int, default=1)
    parser.add_argument("--all", action="store_true", help="process every matching cohort")
    parser.add_argument("--evaluate-only", action="store_true")
    parser.add_argument("--rerun-completed", action="store_true")
    parser.add_argument("--continue-on-failure", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.max_cohorts < 1:
        raise ValueError("--max-cohorts must be positive")
    result = asyncio.run(
        run_batch(
            args.index,
            band=args.band,
            max_cohorts=None if args.all else args.max_cohorts,
            fetch=not args.evaluate_only,
            rerun_completed=args.rerun_completed,
            continue_on_failure=args.continue_on_failure,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
