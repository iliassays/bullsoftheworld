"""Stage one pending US onboarding cohort per night, privately, outside protected market windows.

Runs from a systemd timer (see infra/systemd/bullsofwallst-cohort-staging.*). Each night it walks
the discovery bands in research-priority order and stages the first cohort that has not completed,
using the normal audited batch runner with `promote=False`. Publication remains a separate,
owner-directed decision; nano and ultra-nano bands are excluded because their policy requires an
explicit risk review.

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


def latest_manifest_index(universe_dir: Path) -> Path | None:
    """Pick the newest discovery snapshot; directory names are ISO dates so they sort correctly."""
    candidates = sorted(
        (path for path in universe_dir.glob("*/manifest-index.json") if path.is_file()),
        key=lambda path: path.parent.name,
    )
    return candidates[-1] if candidates else None


async def stage_next_cohort(
    index_path: Path,
    *,
    bands: tuple[str, ...] = BAND_ORDER,
    runner: RunBatch = run_batch,
) -> dict[str, Any]:
    """Stage the first incomplete cohort in band order; report when every band is done."""
    skipped_total = 0
    for band in bands:
        summary = await runner(index_path, band=band, max_cohorts=1, fetch=True)
        if summary.get("failed"):
            return {"outcome": "failed", "band": band, "summary": summary}
        if summary.get("completed"):
            return {"outcome": "staged", "band": band, "summary": summary}
        skipped_total += len(summary.get("skipped", []))
    return {"outcome": "backlog_complete", "bands": list(bands), "skipped": skipped_total}


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
    if index_path is None:
        index_path = latest_manifest_index(DEFAULT_UNIVERSE_DIR)
    if index_path is None or not index_path.is_file():
        log.error("no discovery manifest index found under %s", DEFAULT_UNIVERSE_DIR)
        return 2

    try:
        result = await stage_next_cohort(index_path)
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
            f"band {result['band']}: {json.dumps(failures, default=str)} (index: {index_path})",
        )
        return 1
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage one pending US cohort privately")
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
