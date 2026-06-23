"""Ingestion scheduler - arq cron worker that keeps DSE data fresh on the market's clock.

Replaces the laptop launchd plist. Run it as a long-lived process:

    uv run arq ingestion.worker.WorkerSettings

arq cron fires on the worker's LOCAL clock and has no timezone option, so schedules here are written
in UTC (deploy the worker in UTC - the standard for servers/containers). Bangladesh is UTC+6 with no
DST, so the DSE session 10:00-14:30 Dhaka == 04:00-08:30 UTC, and EOD ~19:00 Dhaka == 13:00 UTC.

Every job still re-checks the Dhaka trading calendar before acting, so a misconfigured host timezone
degrades to "did nothing" rather than "ran at the wrong market time".
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import ClassVar

from arq import cron
from arq.connections import RedisSettings

from bulls.core.config import get_settings
from bulls.market_data.calendar import is_trading_day, is_trading_hours, to_market_tz
from ingestion.history import DAILY_LOOKBACK_DAYS, collect
from ingestion.scheduler import poll_market

log = logging.getLogger(__name__)
MARKET = "DSE"


async def poll_quotes(ctx) -> str:
    """Refresh the delayed quote snapshot - only while the market is open."""
    if not is_trading_hours(dt.datetime.now(dt.UTC)):
        return "skipped: market closed"
    counts = await poll_market(MARKET)
    log.info("intraday poll: %s quotes", counts["quotes"])
    return f"quotes={counts['quotes']}"


async def pull_eod_bars(ctx) -> str:
    """Pull the day's end-of-day bars after the close - only on trading days."""
    today = to_market_tz(dt.datetime.now(dt.UTC)).date()
    if not is_trading_day(today):
        return "skipped: non-trading day"
    stats = await collect(MARKET, days=DAILY_LOOKBACK_DAYS)
    log.info("eod pull: %s bars upserted", stats["bars_upserted"])
    return f"bars={stats['bars_upserted']}"


class WorkerSettings:
    """arq entry point for the ingestion scheduler."""

    functions: ClassVar = [poll_quotes, pull_eod_bars]
    cron_jobs: ClassVar = [
        # Intraday quote refresh: every 30 min across the DSE session (04:00-08:30 UTC).
        cron(poll_quotes, hour={4, 5, 6, 7, 8}, minute={0, 30}, run_at_startup=False),
        # End-of-day bar pull at 13:00 UTC (~19:00 Dhaka, after the EOD publish).
        cron(pull_eod_bars, hour=13, minute=0, run_at_startup=False),
    ]
    redis_settings: ClassVar = RedisSettings.from_dsn(get_settings().redis_url)
