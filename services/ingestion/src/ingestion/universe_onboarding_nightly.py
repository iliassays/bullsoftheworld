"""Stage every cohort the safe nightly window allows, privately, outside protected market windows.

Runs from a systemd timer (see infra/systemd/bullsofwallst-cohort-staging.*). Each night it walks
the discovery bands in research-priority order and keeps staging cohorts - `run_batch` skips ones
already completed, so repeated calls advance through a band's backlog - until either the whole
backlog is staged, a cohort fails, or the safe runtime budget before the next protected window runs
out. Publication remains a separate, owner-directed decision; nano and ultra-nano bands are
excluded because their policy requires an explicit risk review.

    uv run python -m ingestion.universe_onboarding_nightly [--index PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import logging
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx

from bulls.core.config import get_settings
from ingestion.universe_onboarding_batch import run_batch

log = logging.getLogger("universe_onboarding_nightly")

BAND_ORDER = ("small_cap", "micro_cap", "mid_cap")
DEFAULT_UNIVERSE_DIR = Path("var/us-universe")
MAX_RUN_SECONDS = 2 * 60 * 60
MIN_RUN_SECONDS = 30 * 60
PROTECTED_WINDOW_SAFETY_SECONDS = 10 * 60

# The staging job must never compete with the DSE morning watch/session polling or the EOD chain
# on the shared 2-core host. Windows are UTC (server clock), end-exclusive.
PROTECTED_UTC_WINDOWS = (
    (dt.time(3, 15), dt.time(9, 0)),
    (dt.time(12, 45), dt.time(14, 15)),
)

RunBatch = Callable[..., Awaitable[dict[str, Any]]]


def in_protected_window(now: dt.datetime) -> bool:
    moment = now.astimezone(dt.UTC).time()
    return any(start <= moment < end for start, end in PROTECTED_UTC_WINDOWS)


def runtime_budget_seconds(now: dt.datetime) -> int:
    """Return a bounded budget that ends before the next protected market window."""
    utc_now = now.astimezone(dt.UTC)
    starts: list[dt.datetime] = []
    for day_offset in (0, 1):
        day = utc_now.date() + dt.timedelta(days=day_offset)
        for start, _ in PROTECTED_UTC_WINDOWS:
            candidate = dt.datetime.combine(day, start, tzinfo=dt.UTC)
            if candidate > utc_now:
                starts.append(candidate)
    next_protected = min(starts)
    available = int((next_protected - utc_now).total_seconds())
    return max(0, min(MAX_RUN_SECONDS, available - PROTECTED_WINDOW_SAFETY_SECONDS))


def latest_manifest_index(universe_dir: Path) -> Path | None:
    """Pick the newest discovery snapshot; directory names are ISO dates so they sort correctly."""
    candidates = sorted(
        (path for path in universe_dir.glob("*/manifest-index.json") if path.is_file()),
        key=lambda path: path.parent.name,
    )
    return candidates[-1] if candidates else None


async def stage_available_cohorts(
    index_path: Path,
    *,
    bands: tuple[str, ...] = BAND_ORDER,
    runner: RunBatch = run_batch,
    progress: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Stage cohorts across bands until the backlog is exhausted or a cohort fails.

    Keeps staging within a band - one cohort per `run_batch` call, which skips cohorts already
    completed - until a call reports nothing new, then advances to the next band. This uses the
    full nightly window instead of stopping after a single cohort, which previously left most of a
    quiet night's runtime budget unused. `progress` collects every cohort completed across the
    whole call; pass a list in from the caller so a deadline that cuts the loop short
    (`asyncio.timeout`) still leaves visible progress behind after the timeout is caught.
    """
    if progress is None:
        progress = []
    skipped_total = 0
    for band in bands:
        while True:
            summary = await runner(index_path, band=band, max_cohorts=1, fetch=True)
            if summary.get("failed"):
                return {
                    "outcome": "failed",
                    "band": band,
                    "summary": summary,
                    "progress": progress,
                }
            if not summary.get("completed"):
                skipped_total += len(summary.get("skipped", []))
                break
            progress.extend(summary["completed"])
    return {
        "outcome": "backlog_complete",
        "bands": list(bands),
        "skipped": skipped_total,
        "progress": progress,
    }


async def _send_failure_alert(subject: str, body: str) -> None:
    settings = get_settings()
    recipients = [
        address.strip()
        for address in (settings.alert_email or settings.support_email).split(",")
        if address.strip()
    ]
    if not settings.resend_api_key or not recipients:
        log.error("ALERT (email not configured): %s — %s", subject, body)
        return
    async with httpx.AsyncClient(timeout=30) as client:
        await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": recipients,
                "subject": subject,
                "text": body,
            },
        )


async def run_nightly(index_path: Path | None) -> int:
    now = dt.datetime.now(dt.UTC)
    if in_protected_window(now):
        log.info("inside a protected market window at %s UTC; skipping this run", now.time())
        return 0
    runtime_budget = runtime_budget_seconds(now)
    if runtime_budget < MIN_RUN_SECONDS:
        log.info(
            "only %ss remain before the protected-window safety boundary; skipping this run",
            runtime_budget,
        )
        return 0
    if index_path is None:
        index_path = latest_manifest_index(DEFAULT_UNIVERSE_DIR)
    if index_path is None or not index_path.is_file():
        log.error("no discovery manifest index found under %s", DEFAULT_UNIVERSE_DIR)
        return 2

    progress: list[dict[str, Any]] = []
    try:
        async with asyncio.timeout(runtime_budget):
            result = await stage_available_cohorts(index_path, progress=progress)
    except TimeoutError:
        if progress:
            # Graceful stop, not an incident: real progress was made and the run simply reached
            # the safety boundary before the next protected window. Tomorrow's run continues
            # from here (run_batch skips everything already completed).
            log.info(
                "reached the market-safety deadline after staging %d cohort(s) this run",
                len(progress),
            )
            print(
                json.dumps(
                    {
                        "index": str(index_path),
                        "outcome": "deadline_reached",
                        "staged_this_run": len(progress),
                        "cohorts": progress,
                    },
                    indent=2,
                    sort_keys=True,
                    default=str,
                )
            )
            return 0
        await _send_failure_alert(
            "US cohort staging reached its market-safety deadline",
            f"No cohort completed within {runtime_budget}s before the next protected window "
            f"(index: {index_path}). The in-progress cohort may simply be unusually large; "
            "check the log for what it was doing.",
        )
        return 1
    except Exception as error:
        await _send_failure_alert(
            "US cohort staging failed",
            f"{type(error).__name__}: {error} (index: {index_path})",
        )
        raise
    print(json.dumps({"index": str(index_path), **result}, indent=2, sort_keys=True, default=str))
    if result["outcome"] == "failed":
        failures = result["summary"]["failed"]
        await _send_failure_alert(
            "US cohort staging failed",
            f"band {result['band']}: {json.dumps(failures, default=str)} (index: {index_path}; "
            f"{len(result['progress'])} cohort(s) staged before the failure)",
        )
        return 1
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage every pending US cohort the window allows")
    parser.add_argument(
        "--index",
        type=Path,
        default=None,
        help="manifest-index.json path; defaults to the newest snapshot in var/us-universe",
    )
    return parser.parse_args(argv)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    args = _parse_args(sys.argv[1:])
    raise SystemExit(asyncio.run(run_nightly(args.index)))


if __name__ == "__main__":
    main()
