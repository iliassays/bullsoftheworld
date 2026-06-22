"""Ingestion entrypoints.

Run one cycle (cron-friendly):
    uv run python -m ingestion.main DSE

For a long-running scheduler, wire `poll_market` into an arq cron job (Redis) — same pattern as
ai_worker. Kept as a one-shot here so it's trivial to run from cron or a k8s CronJob.
"""

from __future__ import annotations

import asyncio
import sys

from ingestion.scheduler import poll_market


async def _run(market: str) -> None:
    counts = await poll_market(market)
    print(
        f"[ingestion] {market}: persisted {counts['symbols']} symbols, "
        f"{counts['quotes']} quotes; ticks published"
    )


def main() -> None:
    market = sys.argv[1] if len(sys.argv) > 1 else "DSE"
    asyncio.run(_run(market))


if __name__ == "__main__":
    main()
