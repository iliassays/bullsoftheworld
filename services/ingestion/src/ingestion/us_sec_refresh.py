"""On-demand SEC EDGAR/13F coverage refresh with a completion report.

The scheduled crons (`refresh_sec_company_data` daily 06:15 UTC, `refresh_sec_institutional_data`
weekly Sunday 10:00 UTC) already scope correctly to the ready/research_only universe. A gap opens
whenever the ready universe grows mid-day (a cohort onboarding run) after that day's cron already
executed: coverage stays keyed to the old, smaller universe until the next scheduled run. This
script closes that gap on demand instead of waiting, and always reports what it did.

    uv run python -m ingestion.us_sec_refresh
    uv run python -m ingestion.us_sec_refresh --13f   # also refresh 13F (parses a 95+MiB archive)
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys

import httpx
from sqlalchemy import func, select

from bulls.core.config import get_settings
from bulls.core.db import get_sessionmaker
from bulls.core.models import RegulatoryDataState, Symbol
from ingestion.sec import collect as refresh_sec_evidence
from ingestion.sec_13f import collect as refresh_sec_13f
from ingestion.sec_watchdog import MARKET, _database_problems


async def _ready_symbol_count() -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(Symbol)
                .where(
                    Symbol.market == MARKET,
                    Symbol.is_active.is_(True),
                    Symbol.is_hidden.is_(False),
                    Symbol.data_status == "ready",
                )
            )
            or 0
        )


async def _coverage_snapshot() -> dict[str, int]:
    sm = get_sessionmaker()
    async with sm() as session:
        rows = list(
            await session.scalars(
                select(RegulatoryDataState).where(RegulatoryDataState.market == MARKET)
            )
        )
    return {row.source: row.symbols_covered for row in rows}


async def _send_report(lines: list[str]) -> None:
    settings = get_settings()
    recipients = [
        value.strip()
        for value in (
            settings.wallst_alert_email or settings.alert_email or settings.support_email
        ).split(",")
        if value.strip()
    ]
    if not settings.resend_api_key or not recipients:
        print("(email not configured; report above only)")
        return
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": recipients,
                "subject": "Bulls of Wall Street - SEC coverage refresh complete",
                "text": "\n".join(lines),
            },
        )
    if response.status_code >= 300:
        print(f"report email failed {response.status_code}: {response.text}")


async def run(*, include_13f: bool) -> int:
    ready = await _ready_symbol_count()
    before = await _coverage_snapshot()

    stats: dict[str, dict] = {}
    stats["sec_edgar"] = await refresh_sec_evidence()
    if include_13f:
        stats["sec_13f"] = await refresh_sec_13f()

    after = await _coverage_snapshot()
    remaining_problems = await _database_problems(dt.datetime.now(dt.UTC))

    lines = [
        f"SEC coverage refresh completed at {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M UTC}",
        f"Ready US symbols: {ready}",
        "",
    ]
    for source in ("sec_edgar", "sec_13f"):
        if source not in after and source != "sec_edgar":
            continue
        lines.append(f"{source}: {before.get(source, 0)} -> {after.get(source, 0)} symbols covered")
    lines.append("")
    if remaining_problems:
        lines.append("Remaining watchdog problems:")
        lines.extend(f"- {problem}" for problem in remaining_problems)
    else:
        lines.append("Watchdog: all US data health checks pass.")

    report = "\n".join(lines)
    print(report)
    await _send_report(lines)
    return 1 if remaining_problems else 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh US SEC coverage on demand")
    parser.add_argument(
        "--13f",
        dest="include_13f",
        action="store_true",
        help="also refresh Form 13F (parses a 95+MiB archive; heavier, use sparingly)",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args(sys.argv[1:])
    raise SystemExit(asyncio.run(run(include_13f=args.include_13f)))


if __name__ == "__main__":
    main()
