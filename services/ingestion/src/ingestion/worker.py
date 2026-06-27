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
from ingestion import news
from ingestion.analytics import compute_all
from ingestion.buzz import snapshot_all
from ingestion.company import collect as collect_company
from ingestion.history import DAILY_LOOKBACK_DAYS, collect
from ingestion.market_summary import DAILY_LOOKBACK_DAYS as SUMMARY_LOOKBACK_DAYS
from ingestion.market_summary import collect as collect_summary
from ingestion.scheduler import poll_market
from ingestion.signals.news_agents import run_news_agents
from ingestion.signals.runner import (
    run_factor_agents,
    run_levels_agent,
    run_market_update,
    run_ownership_agents,
    run_volume_agent,
)

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


async def pull_eod_summary(ctx) -> str:
    """Pull the day's market-wide summary (index/turnover/cap) after the close — trading days only."""
    today = to_market_tz(dt.datetime.now(dt.UTC)).date()
    if not is_trading_day(today):
        return "skipped: non-trading day"
    stats = await collect_summary(MARKET, days=SUMMARY_LOOKBACK_DAYS)
    log.info("eod summary: %s days upserted", stats["days_upserted"])
    return f"summary={stats['days_upserted']}"


async def refresh_company(ctx) -> str:
    """Weekly company reference + shareholding refresh. Heavy/slow-moving — runs off the EOD path."""
    stats = await collect_company(MARKET)
    log.info("company refresh: %s/%s profiles", stats["profiles"], stats["symbols"])
    return f"profiles={stats['profiles']} shareholding={stats['shareholding_rows']}"


async def refresh_analytics(ctx) -> str:
    """Recompute + persist the analytics snapshot for every symbol — only on trading days."""
    today = to_market_tz(dt.datetime.now(dt.UTC)).date()
    if not is_trading_day(today):
        return "skipped: non-trading day"
    counts = await compute_all(MARKET)
    log.info("analytics refresh: %s/%s symbols", counts["computed"], counts["symbols"])
    return f"analytics={counts['computed']}"


async def snapshot_buzz(ctx) -> str:
    """Snapshot each symbol's daily social attention — only on trading days.

    Runs through the session and again at EOD; the upsert keeps today's (market, code, date) row
    current, so watchers_total and the day's counts stay fresh and the history is resilient if the
    EOD run is missed. The displayed /buzz trend doesn't depend on when this runs — today's row is
    excluded from the baseline — so this is about freshness/robustness, not changing the signal.
    """
    today = to_market_tz(dt.datetime.now(dt.UTC)).date()
    if not is_trading_day(today):
        return "skipped: non-trading day"
    counts = await snapshot_all(MARKET)
    log.info("buzz snapshot: %s symbols", counts["symbols"])
    return f"buzz={counts['symbols']}"


async def run_signals(ctx) -> str:
    """Publish agent desk-notes from the day's confirmed levels — only on trading days."""
    today = to_market_tz(dt.datetime.now(dt.UTC)).date()
    if not is_trading_day(today):
        return "skipped: non-trading day"
    counts = await run_levels_agent(MARKET)
    log.info("signals: %s notes published", counts["published"])
    return f"signals={counts['published']}"


async def run_ownership_signals(ctx) -> str:
    """Publish ownership desk-notes after the weekly company/shareholding refresh."""
    counts = await run_ownership_agents(MARKET)
    log.info("ownership signals: %s notes published", counts["published"])
    return f"ownership={counts['published']}"


async def run_volume_signals(ctx) -> str:
    """Flag unusual intraday volume — only while the market is open."""
    if not is_trading_hours(dt.datetime.now(dt.UTC)):
        return "skipped: market closed"
    counts = await run_volume_agent(MARKET)
    log.info("volume signals: %s notes published", counts["published"])
    return f"volume={counts['published']}"


async def pull_news(ctx) -> str:
    """Onboard DSE news (classify + score, drop noise), then fire the news agents on new items."""
    counts = await news.collect(MARKET, days=news.DAILY_LOOKBACK_DAYS)
    sig = await run_news_agents(MARKET)
    log.info("news: kept %s / %s fetched, %s notes", counts["kept"], counts["fetched"], sig["published"])
    return f"news_kept={counts['kept']} notes={sig['published']}"


async def run_market_signals(ctx) -> str:
    """Post the daily market-wide close wrap — only on trading days."""
    today = to_market_tz(dt.datetime.now(dt.UTC)).date()
    if not is_trading_day(today):
        return "skipped: non-trading day"
    counts = await run_market_update(MARKET)
    log.info("market wrap: %s published", counts["published"])
    return f"market={counts['published']}"


async def run_factor_signals(ctx) -> str:
    """Descriptive factor notes (momentum / quality / smart-money / relative strength), after the
    analytics recompute — only on trading days."""
    today = to_market_tz(dt.datetime.now(dt.UTC)).date()
    if not is_trading_day(today):
        return "skipped: non-trading day"
    counts = await run_factor_agents(MARKET)
    log.info("factor signals: %s notes published", counts["published"])
    return f"factors={counts['published']}"


class WorkerSettings:
    """arq entry point for the ingestion scheduler."""

    functions: ClassVar = [
        poll_quotes,
        pull_eod_bars,
        pull_eod_summary,
        refresh_company,
        refresh_analytics,
        snapshot_buzz,
        run_signals,
        run_ownership_signals,
        run_volume_signals,
        run_market_signals,
        run_factor_signals,
        pull_news,
    ]
    cron_jobs: ClassVar = [
        # Intraday quote refresh: every 15 min across the DSE session (~04:00-08:45 UTC = 10:00-14:45 BDT).
        cron(poll_quotes, hour={4, 5, 6, 7, 8}, minute={0, 15, 30, 45}, run_at_startup=False),
        # End-of-day bar pull at 13:00 UTC (~19:00 Dhaka, after the EOD publish).
        cron(pull_eod_bars, hour=13, minute=0, run_at_startup=False),
        # Market-wide summary (index/turnover) right after the bar pull.
        cron(pull_eod_summary, hour=13, minute=5, run_at_startup=False),
        # Weekly company/shareholding sweep — Friday (DSE closed, site quiet), well off the EOD path.
        cron(refresh_company, weekday="fri", hour=14, minute=0, run_at_startup=False),
        # Recompute analytics 15 min after the bar pull, so the screener is fresh by night.
        cron(refresh_analytics, hour=13, minute=15, run_at_startup=False),
        # Snapshot social attention hourly across the session, then finalize after the bar pull.
        # Intraday runs keep watchers_total + today's counts fresh; the 13:20 run is the EOD row.
        cron(snapshot_buzz, hour={4, 5, 6, 7, 8, 13}, minute=20, run_at_startup=False),
        # Agent desk-notes from the day's confirmed levels, after analytics is fresh.
        cron(run_signals, hour=13, minute=25, run_at_startup=False),
        # Ownership desk-notes after the weekly company/shareholding refresh (Fri 14:00).
        cron(run_ownership_signals, weekday="fri", hour=14, minute=10, run_at_startup=False),
        # Unusual-volume notes mid/late session, after the :30 quote polls.
        cron(run_volume_signals, hour={5, 6, 7, 8}, minute=45, run_at_startup=False),
        # Market-wide close wrap, after the EOD summary lands.
        cron(run_market_signals, hour=13, minute=30, run_at_startup=False),
        # Factor notes (momentum / quality / smart-money / relative strength), after analytics (13:15).
        cron(run_factor_signals, hour=13, minute=40, run_at_startup=False),
        # News: pre-open (03:30 UTC ≈ 09:30 Dhaka) so overnight items are in before the bell,
        # and after the close (13:35 UTC) to catch intraday postings.
        cron(pull_news, hour={3, 13}, minute=35, run_at_startup=False),
    ]
    redis_settings: ClassVar = RedisSettings.from_dsn(get_settings().redis_url)
