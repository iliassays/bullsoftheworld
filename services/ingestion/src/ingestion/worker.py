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

import httpx
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import func, select

from bulls.core.config import get_settings
from bulls.core.db import get_sessionmaker, verify_runtime_database_role
from bulls.core.models import DailyBar, MarketSummary
from bulls.market_data.calendar import is_trading_day, is_trading_hours, to_market_tz
from ingestion import news
from ingestion.agent_trader import run_agents
from ingestion.analytics import compute_all
from ingestion.block_trades import pull_block_trades as collect_block_trades
from ingestion.buzz import snapshot_all
from ingestion.company import collect as collect_company
from ingestion.growth_retention import prune_raw_events
from ingestion.history import DAILY_LOOKBACK_DAYS, collect
from ingestion.market_summary import DAILY_LOOKBACK_DAYS as SUMMARY_LOOKBACK_DAYS
from ingestion.market_summary import collect as collect_summary
from ingestion.portfolio_snapshot import run as snapshot_portfolios_run
from ingestion.scheduler import poll_market
from ingestion.signals.news_agents import run_news_agents
from ingestion.signals.runner import (
    run_factor_agents,
    run_levels_agent,
    run_market_update,
    run_ownership_agents,
    run_volume_agent,
)
from ingestion.trending import compute_trending

log = logging.getLogger(__name__)
MARKET = "DSE"
TENANT_ID = "bullsofdhaka"
EOD_START_UTC_HOUR = 11
FINAL_QUOTE_UTC_HOUR = 8
FINAL_QUOTE_UTC_MINUTE = 45
_EOD_CHAIN_VERSION = "v2"
_EOD_COMPLETION_TTL_S = 400 * 24 * 60 * 60


async def startup(ctx) -> None:
    await verify_runtime_database_role()


def _eod_completion_key(market_date: dt.date) -> str:
    return f"ingestion:{TENANT_ID}:eod-complete:{_EOD_CHAIN_VERSION}:{market_date}"


def _after_market_date_utc_time(
    now: dt.datetime, market_date: dt.date, hour: int, minute: int = 0
) -> bool:
    """True once the UTC schedule for a Dhaka market date has passed.

    At 18:00-23:59 UTC the Dhaka calendar has already rolled to tomorrow, but tomorrow's
    UTC-scheduled jobs are still in the future. Startup jobs must not run just because the Dhaka
    date changed.
    """
    due = dt.datetime.combine(market_date, dt.time(hour=hour, minute=minute, tzinfo=dt.UTC))
    return now >= due


def _after_eod_window(now: dt.datetime | None = None) -> bool:
    """True once the DSE close/EOD data window has started for the Dhaka market date."""
    now = now or dt.datetime.now(dt.UTC)
    market_date = to_market_tz(now).date()
    return _after_market_date_utc_time(now, market_date, EOD_START_UTC_HOUR)


async def poll_quotes(ctx) -> str:
    """Refresh the delayed quote snapshot - only while the market is open."""
    if not is_trading_hours(dt.datetime.now(dt.UTC)):
        return "skipped: market closed"
    counts = await poll_market(MARKET, tenant_id=TENANT_ID)
    log.info("intraday poll: %s quotes", counts["quotes"])
    return f"quotes={counts['quotes']}"


async def finalize_quotes(ctx) -> str:
    """Capture the final delayed snapshot after close, including startup recovery."""
    now = dt.datetime.now(dt.UTC)
    today = to_market_tz(now).date()
    if not is_trading_day(today):
        return "skipped: non-trading day"
    if not _after_market_date_utc_time(
        now,
        today,
        FINAL_QUOTE_UTC_HOUR,
        FINAL_QUOTE_UTC_MINUTE,
    ):
        return "skipped: before final quote window"
    counts = await poll_market(MARKET, tenant_id=TENANT_ID)
    log.info("final delayed quote poll: %s quotes", counts["quotes"])
    return f"quotes={counts['quotes']}"


async def run_agent_portfolios(ctx) -> str:
    """One trading tick for the five agent model portfolios — settle, exits, entries. Runs 3 min
    after each intraday quote poll so it always sees the freshest snapshot; the engine itself
    no-ops outside trading hours and refuses stale quotes, so a mistimed run does nothing."""
    counts = await run_agents(MARKET, tenant_id=TENANT_ID)
    if counts.get("skipped"):
        return "skipped: market closed"
    log.info("agent portfolios: %s", counts)
    return f"agents={counts['agents']} buys={counts['buys']} sells={counts['sells']}"


async def pull_eod_bars(ctx) -> str:
    """Pull the day's end-of-day bars after the close - only on trading days."""
    if not _after_eod_window():
        return "skipped: before EOD window"
    today = to_market_tz(dt.datetime.now(dt.UTC)).date()
    if not is_trading_day(today):
        return "skipped: non-trading day"
    stats = await collect(MARKET, days=DAILY_LOOKBACK_DAYS)
    log.info("eod pull: %s bars upserted", stats["bars_upserted"])
    return f"bars={stats['bars_upserted']}"


async def pull_eod_summary(ctx) -> str:
    """Pull the day's market-wide summary (index/turnover/cap) after the close — trading days only."""
    if not _after_eod_window():
        return "skipped: before EOD window"
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
    if not _after_eod_window():
        return "skipped: before EOD window"
    today = to_market_tz(dt.datetime.now(dt.UTC)).date()
    if not is_trading_day(today):
        return "skipped: non-trading day"
    counts = await compute_all(MARKET)
    log.info(
        "analytics refresh: %s/%s symbols, %s chart patterns",
        counts["computed"],
        counts["symbols"],
        counts["patterns"],
    )
    return f"analytics={counts['computed']} patterns={counts['patterns']}"


async def snapshot_portfolios(ctx) -> str:
    """Daily portfolio value snapshot (growth-over-time chart) — only on trading days, once EOD
    quotes have settled (the last intraday poll ~08:45 UTC is effectively the close)."""
    if not _after_eod_window():
        return "skipped: before EOD window"
    today = to_market_tz(dt.datetime.now(dt.UTC)).date()
    if not is_trading_day(today):
        return "skipped: non-trading day"
    stats = await snapshot_portfolios_run(MARKET, tenant_id=TENANT_ID)
    log.info("portfolio snapshot: %s users", stats["users"])
    return f"users={stats['users']}"


async def recover_eod_chain(ctx) -> str:
    """Ordered EOD recovery path used on worker startup and as a post-close safety net.

    Normal cron jobs stay split for observability, but startup recovery must be sequential:
    bars -> summary -> analytics -> portfolios -> activity/signals. Running these as independent
    startup cron jobs can race analytics ahead of the bar pull.
    """
    if not _after_eod_window():
        return "skipped: before EOD window"
    today = to_market_tz(dt.datetime.now(dt.UTC)).date()
    if not is_trading_day(today):
        return "skipped: non-trading day"

    redis = ctx.get("redis") if ctx else None
    completion_key = _eod_completion_key(today)
    if redis is not None and await redis.get(completion_key):
        return f"skipped: {today} EOD chain already complete"

    bars = await collect(MARKET, days=DAILY_LOOKBACK_DAYS)
    summary = await collect_summary(MARKET, days=SUMMARY_LOOKBACK_DAYS)
    async with get_sessionmaker()() as session:
        latest_bar = await session.scalar(
            select(func.max(DailyBar.date)).where(DailyBar.market == MARKET)
        )
        latest_summary = await session.scalar(
            select(func.max(MarketSummary.date)).where(MarketSummary.market == MARKET)
        )
    if latest_bar != today or latest_summary != today:
        # The first attempt is intentionally early. A source that has not published yet is normal;
        # downstream analytics must never run against yesterday while appearing current.
        return (
            f"pending: source not published for {today} "
            f"(bars={latest_bar}, summary={latest_summary})"
        )

    analytics = await compute_all(MARKET)
    portfolios = await snapshot_portfolios_run(MARKET, tenant_id=TENANT_ID)
    trending = await compute_trending(MARKET)
    buzz = await snapshot_all(MARKET, tenant_id=TENANT_ID)
    levels = await run_levels_agent(MARKET, tenant_id=TENANT_ID)
    factors = await run_factor_agents(MARKET, tenant_id=TENANT_ID)
    market_note = await run_market_update(MARKET, tenant_id=TENANT_ID)
    if redis is not None:
        await redis.set(completion_key, "1", ex=_EOD_COMPLETION_TTL_S)
    log.info(
        "eod recovery: bars=%s summary=%s analytics=%s portfolios=%s trending=%s "
        "buzz=%s levels=%s factors=%s market=%s",
        bars["bars_upserted"],
        summary["days_upserted"],
        analytics["computed"],
        portfolios["users"],
        trending["stored"],
        buzz["symbols"],
        levels["published"],
        factors["published"],
        market_note["published"],
    )
    return (
        f"recovered bars={bars['bars_upserted']} summary={summary['days_upserted']} "
        f"analytics={analytics['computed']} portfolios={portfolios['users']} "
        f"trending={trending['stored']} buzz={buzz['symbols']} levels={levels['published']} "
        f"factors={factors['published']} market={market_note['published']}"
    )


async def run_trending(ctx) -> str:
    """Recompute the daily 'Watch today' activity ranking — only on trading days, after analytics."""
    now = dt.datetime.now(dt.UTC)
    today = to_market_tz(now).date()
    if not _after_market_date_utc_time(now, today, 13, 25):
        return "skipped: before trending window"
    if not is_trading_day(today):
        return "skipped: non-trading day"
    stats = await compute_trending(MARKET)
    log.info(
        "trending: stored %s of %s eligible (as_of %s)",
        stats["stored"],
        stats["eligible"],
        stats["as_of"],
    )
    return f"trending={stats['stored']}"


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
    counts = await snapshot_all(MARKET, tenant_id=TENANT_ID)
    log.info("buzz snapshot: %s symbols", counts["symbols"])
    return f"buzz={counts['symbols']}"


async def run_signals(ctx) -> str:
    """Publish agent desk-notes from the day's confirmed levels — only on trading days."""
    now = dt.datetime.now(dt.UTC)
    today = to_market_tz(now).date()
    if not _after_market_date_utc_time(now, today, 13, 25):
        return "skipped: before signals window"
    if not is_trading_day(today):
        return "skipped: non-trading day"
    counts = await run_levels_agent(MARKET, tenant_id=TENANT_ID)
    log.info("signals: %s notes published", counts["published"])
    return f"signals={counts['published']}"


async def run_ownership_signals(ctx) -> str:
    """Publish ownership desk-notes after the weekly company/shareholding refresh."""
    now = dt.datetime.now(dt.UTC)
    today = to_market_tz(now).date()
    if today.weekday() != 4 or not _after_market_date_utc_time(now, today, 14, 10):
        return "skipped: before ownership window"
    counts = await run_ownership_agents(MARKET, tenant_id=TENANT_ID)
    log.info("ownership signals: %s notes published", counts["published"])
    return f"ownership={counts['published']}"


async def run_volume_signals(ctx) -> str:
    """Flag unusual intraday volume — only while the market is open."""
    if not is_trading_hours(dt.datetime.now(dt.UTC)):
        return "skipped: market closed"
    counts = await run_volume_agent(MARKET, tenant_id=TENANT_ID)
    log.info("volume signals: %s notes published", counts["published"])
    return f"volume={counts['published']}"


async def pull_news(ctx) -> str:
    """Onboard DSE news (classify + score, drop noise), then fire the news agents on new items."""
    counts = await news.collect(MARKET, days=news.DAILY_LOOKBACK_DAYS)
    sig = await run_news_agents(MARKET, tenant_id=TENANT_ID)
    log.info(
        "news: kept %s / %s fetched, %s notes", counts["kept"], counts["fetched"], sig["published"]
    )
    return f"news_kept={counts['kept']} notes={sig['published']}"


async def pull_block_trades(ctx) -> str:
    """Daily per-scrip block-market list — INTERNAL dataset (admin-only; no public surface).

    Sourced from LankaBD pending the ToS decision (docs/redesign/2026-07-drops.md); one request
    per trading day, after the session closes."""
    today = to_market_tz(dt.datetime.now(dt.UTC)).date()
    if not is_trading_day(today):
        return "skipped: non-trading day"
    counts = await collect_block_trades(MARKET)
    log.info("block trades: stored %s / %s fetched", counts["stored"], counts["fetched"])
    return f"block_trades={counts['stored']}"


async def _trigger_publish(paths: list[str]) -> dict[str, str]:
    """POST each publish path against the API (posting + dedupe live there). Idempotent per day,
    so a manual publish or a re-run won't double-post; one path failing won't break the others."""
    s = get_settings()
    if not s.admin_token:
        return {"_": "skipped: no ADMIN_TOKEN"}
    headers = {"X-Admin-Token": s.admin_token, "X-Tenant-Host": "bullsofdhaka.com"}
    base = s.api_public_url.rstrip("/")
    out: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=90) as client:
        for p in paths:
            name = p.rsplit("=", 1)[-1] + ("·feed" if "publish-feed" in p else "")
            try:
                r = await client.post(f"{base}{p}", headers=headers)
                out[name] = (
                    r.json().get("status", "ok") if r.status_code < 300 else f"err{r.status_code}"
                )
            except Exception as e:
                out[name] = f"error: {type(e).__name__}"
    return out


async def run_market_signals(ctx) -> str:
    """Daily Evening Wrap card → in-app feed AND Facebook, after the close. Trading days only."""
    now = dt.datetime.now(dt.UTC)
    today = to_market_tz(now).date()
    if not _after_market_date_utc_time(now, today, 13, 50):
        return "skipped: before evening window"
    if not is_trading_day(today):
        return "skipped: non-trading day"
    res = await _trigger_publish(
        ["/admin/fb/publish-feed?kind=evening_wrap", "/admin/fb/publish?kind=evening_wrap"]
    )
    log.info("evening wrap auto-post: %s", res)
    return f"evening {res}"


async def run_morning_watch(ctx) -> str:
    """Pre-open Morning Watch card → Facebook only. Trading days only."""
    now = dt.datetime.now(dt.UTC)
    today = to_market_tz(now).date()
    if not _after_market_date_utc_time(now, today, 3, 30):
        return "skipped: before morning window"
    if not is_trading_day(today):
        return "skipped: non-trading day"
    res = await _trigger_publish(["/admin/fb/publish?kind=morning_watch"])
    log.info("morning watch auto-post: %s", res)
    return f"morning {res}"


async def run_earnings_week(ctx) -> str:
    """Sunday-morning earnings-calendar card → Facebook, before the trading week opens.
    The composer skips (CardError) when no earnings are scheduled — no filler posts."""
    now = dt.datetime.now(dt.UTC)
    today = to_market_tz(now).date()
    if today.weekday() != 6 or not _after_market_date_utc_time(now, today, 2, 45):
        return "skipped: before earnings-week window"
    res = await _trigger_publish(["/admin/fb/publish?kind=earnings_week"])
    log.info("earnings week auto-post: %s", res)
    return f"earnings_week {res}"


async def run_mood_card(ctx) -> str:
    """Dhaka Mood gauge card → Facebook at evening prime time. Trading days only."""
    now = dt.datetime.now(dt.UTC)
    today = to_market_tz(now).date()
    if not _after_market_date_utc_time(now, today, 15, 0):
        return "skipped: before mood window"
    if not is_trading_day(today):
        return "skipped: non-trading day"
    res = await _trigger_publish(["/admin/fb/publish?kind=mood"])
    log.info("mood card auto-post: %s", res)
    return f"mood {res}"


async def run_weekly_recap(ctx) -> str:
    """Weekly recap card → Facebook only. Fires Thursday after close (cron weekday)."""
    now = dt.datetime.now(dt.UTC)
    today = to_market_tz(now).date()
    if today.weekday() != 3 or not _after_market_date_utc_time(now, today, 14, 0):
        return "skipped: before weekly-recap window"
    if not is_trading_day(today):
        return "skipped: non-trading day"
    res = await _trigger_publish(["/admin/fb/publish?kind=weekly_recap"])
    log.info("weekly recap auto-post: %s", res)
    return f"weekly {res}"


async def run_factor_signals(ctx) -> str:
    """Descriptive factor notes (momentum / quality / smart-money / relative strength), after the
    analytics recompute — only on trading days."""
    now = dt.datetime.now(dt.UTC)
    today = to_market_tz(now).date()
    if not _after_market_date_utc_time(now, today, 13, 40):
        return "skipped: before factor window"
    if not is_trading_day(today):
        return "skipped: non-trading day"
    counts = await run_factor_agents(MARKET, tenant_id=TENANT_ID)
    log.info("factor signals: %s notes published", counts["published"])
    return f"factors={counts['published']}"


async def prune_growth_analytics(ctx) -> str:
    """Delete raw, pseudonymous funnel/page-view events after their 180-day analysis window."""
    counts = await prune_raw_events()
    log.info("growth analytics retention: %s", counts)
    return f"product_events={counts['product_events']} page_views={counts['page_view_events']}"


class WorkerSettings:
    on_startup: ClassVar = startup
    """arq entry point for the ingestion scheduler."""

    functions: ClassVar = [
        poll_quotes,
        finalize_quotes,
        run_agent_portfolios,
        pull_eod_bars,
        pull_eod_summary,
        refresh_company,
        refresh_analytics,
        snapshot_portfolios,
        recover_eod_chain,
        run_trending,
        snapshot_buzz,
        run_signals,
        run_ownership_signals,
        run_volume_signals,
        run_market_signals,
        run_factor_signals,
        pull_news,
        pull_block_trades,
        run_earnings_week,
        run_mood_card,
        prune_growth_analytics,
    ]
    cron_jobs: ClassVar = [
        # Intraday quote refresh: every 15 min across the DSE session (~04:00-08:45 UTC = 10:00-14:45 BDT).
        cron(poll_quotes, hour={4, 5, 6, 7, 8}, minute={0, 15, 30, 45}, run_at_startup=True),
        # The provider is delayed, so the final close is not observable at 14:30 BDT. Capture it
        # at 14:45 and recover it on a post-close restart without widening trading-hours guards.
        cron(
            finalize_quotes,
            hour=FINAL_QUOTE_UTC_HOUR,
            minute=FINAL_QUOTE_UTC_MINUTE,
            run_at_startup=True,
        ),
        # Agent model portfolios: 3 min after each quote poll (fresh snapshot, no race with it).
        cron(
            run_agent_portfolios, hour={4, 5, 6, 7, 8}, minute={3, 18, 33, 48}, run_at_startup=False
        ),
        # Early ordered attempts at 17:00/18:00 Dhaka put research in the user's 1-3h post-close
        # window whenever the source is ready. Freshness gates make an unpublished source a clean
        # pending result; the canonical 19:00 jobs and 20:05 recovery remain the safety net.
        cron(recover_eod_chain, hour={11, 12}, minute=0, run_at_startup=False),
        # Canonical end-of-day bar pull at 13:00 UTC (~19:00 Dhaka).
        cron(pull_eod_bars, hour=13, minute=0, run_at_startup=False),
        # Market-wide summary (index/turnover) right after the bar pull.
        cron(pull_eod_summary, hour=13, minute=5, run_at_startup=False),
        # Weekly company/shareholding sweep — Friday (DSE closed, site quiet), well off the EOD path.
        cron(refresh_company, weekday="fri", hour=14, minute=0, run_at_startup=False),
        # Recompute analytics 15 min after the bar pull, so the screener is fresh by night.
        cron(refresh_analytics, hour=13, minute=15, run_at_startup=False),
        # Portfolio growth-chart snapshot — 20 min after the bar pull, same cadence as the other
        # once-daily EOD jobs. Idempotent (upsert by user+date); no weekday filter needed since
        # the task itself skips non-trading days.
        cron(snapshot_portfolios, hour=13, minute=20, run_at_startup=False),
        # Sequential safety net: catches a missed EOD chain and gives watchdog restarts a real
        # recovery action after close, without racing analytics ahead of the bar pull.
        cron(recover_eod_chain, hour=14, minute=5, run_at_startup=True),
        # 'Watch today' activity ranking — after analytics, before the FB market signals (13:50).
        # run_at_startup=True: confirmed live (2026-07-06) that arq's cron loop can silently stall
        # for ~30 min without any restart or error — pull_eod_summary/refresh_analytics/snapshot_*
        # ran fine at 13:05-13:20, then run_trending/run_signals(13:25)/pull_news(13:35)/
        # run_factor_signals(13:40) never even logged a start, before run_market_signals(13:50)
        # ran normally again. A missed exact-minute tick used to mean silence for the rest of the
        # day. All the jobs below are cheap (pure DB read/compute, no external scraping) and
        # idempotent (upsert or a dedupe key per day), so catching up on the next worker restart —
        # from a deploy or the watchdog's own restart-on-fault — is free and safe.
        cron(run_trending, hour=13, minute=25, run_at_startup=True),
        # Snapshot social attention hourly across the session, then finalize after the bar pull.
        # Intraday runs keep watchers_total + today's counts fresh; the 13:20 run is the EOD row.
        cron(snapshot_buzz, hour={4, 5, 6, 7, 8, 13}, minute=20, run_at_startup=False),
        # Agent desk-notes from the day's confirmed levels, after analytics is fresh.
        cron(run_signals, hour=13, minute=25, run_at_startup=True),
        # Ownership desk-notes after the weekly company/shareholding refresh (Fri 14:00).
        cron(run_ownership_signals, weekday="fri", hour=14, minute=10, run_at_startup=True),
        # Unusual-volume notes mid/late session, after the :30 quote polls.
        cron(run_volume_signals, hour={5, 6, 7, 8}, minute=45, run_at_startup=True),
        # Evening Wrap card → in-app feed + Facebook, after EOD summary/analytics/factor notes
        # land (13:05/13:15/13:40 UTC ≈ 19:40 Dhaka). Trading days only; idempotent per day.
        cron(run_market_signals, hour=13, minute=50, run_at_startup=True),
        # Morning Watch card → Facebook only, pre-open (03:30 UTC ≈ 09:30 Dhaka, before 10:00 open).
        cron(run_morning_watch, hour=3, minute=30, run_at_startup=True),
        # Weekly Recap card → Facebook only, Thursday after close (14:00 UTC ≈ 20:00 Dhaka).
        # arq's weekday tuple is ('mon','tues','wed','thurs','fri','sat','sun') — it's "thurs", not "thu".
        # A value not in that tuple makes WEEKDAYS.index() throw on boot and crash-loops the whole worker.
        cron(run_weekly_recap, weekday="thurs", hour=14, minute=0, run_at_startup=True),
        # Factor notes (momentum / quality / smart-money / relative strength), after analytics (13:15).
        cron(run_factor_signals, hour=13, minute=40, run_at_startup=True),
        # News: pre-open (03:30 UTC ≈ 09:30 Dhaka) so overnight items are in before the bell,
        # and after the close (13:35 UTC) to catch intraday postings. Kept run_at_startup=False:
        # this one does hit the external DSE site, and restarts can be frequent during a deploy
        # day — no need to add redundant scrape load on top of its own two scheduled runs.
        cron(pull_news, hour={3, 13}, minute=35, run_at_startup=False),
        # Earnings-week logo calendar: Sunday 08:45 Dhaka, before the week opens.
        cron(run_earnings_week, weekday="sun", hour=2, minute=45, run_at_startup=True),
        # Dhaka Mood gauge: 21:00 Dhaka — Bangladesh Facebook prime time, clear of the wrap.
        cron(run_mood_card, hour=15, minute=0, run_at_startup=True),
        # Block-market list, once after the close (session ends 08:30 UTC); internal dataset.
        # No weekday filter — arq only accepts a single weekday string (a comma-joined list
        # crash-loops the whole worker); the task itself skips non-trading days.
        cron(pull_block_trades, hour=9, minute=30, run_at_startup=False),
        # Raw product/page-view events are operational analytics, not a permanent user profile.
        cron(prune_growth_analytics, weekday="sun", hour=1, minute=30, run_at_startup=False),
    ]
    redis_settings: ClassVar = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name: ClassVar = get_settings().dse_ingestion_queue_name
