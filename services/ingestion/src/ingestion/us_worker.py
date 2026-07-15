"""Dedicated US EOD scheduler.

The US bootstrap provider is EOD-only, so this worker never fabricates intraday quotes. It uses a
separate Redis queue and a coverage gate before publishing analytics. Reference-only symbols are
onboarded explicitly by the backfill CLI; daily runs touch only retail-ready cohorts.

Run in a UTC process:

    uv run arq ingestion.us_worker.WorkerSettings
"""

from __future__ import annotations

import datetime as dt
import logging
import math
from typing import ClassVar

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import func, select

from bulls.core.config import get_settings
from bulls.core.db import bind_tenant_context, get_sessionmaker, verify_runtime_database_role
from bulls.core.markets import US_VERIFIED_CALENDAR_YEARS
from bulls.core.models import DailyBar, QuoteSnapshot, Symbol
from bulls.market_data.calendar import (
    is_trading_day,
    market_close_on,
    market_timezone,
    to_market_tz,
)
from ingestion.alerts import check_price_alerts
from ingestion.analytics import compute_all
from ingestion.buzz import snapshot_all
from ingestion.finra_short import collect as collect_finra_short
from ingestion.history import US_DAILY_LOOKBACK_DAYS, collect
from ingestion.portfolio_snapshot import run as snapshot_portfolios
from ingestion.restricted_research import refresh_restricted_market_data
from ingestion.security_master import collect as refresh_security_master
from ingestion.signals.runner import (
    run_eod_volume_agent,
    run_factor_agents,
    run_levels_agent,
    run_market_update,
    run_short_flow_agent,
)
from ingestion.us_eod_snapshot import collect as publish_us_eod

log = logging.getLogger(__name__)
MARKET = "US"
TENANT_ID = "bullsofwallst"
EOD_PUBLICATION_DELAY = dt.timedelta(minutes=90)
_COMPLETION_TTL_S = 400 * 24 * 60 * 60
_CHAIN_VERSION = "v2"


async def startup(ctx) -> None:
    await verify_runtime_database_role()


def _completion_key(session_date: dt.date) -> str:
    return f"ingestion:{TENANT_ID}:eod-complete:{_CHAIN_VERSION}:{session_date.isoformat()}"


def most_recent_due_session(now: dt.datetime) -> dt.date:
    """Latest US session whose close plus provider-publication delay has elapsed."""
    local = to_market_tz(now, market=MARKET)
    candidate = local.date()
    if is_trading_day(candidate, market=MARKET):
        due = (
            dt.datetime.combine(
                candidate,
                market_close_on(candidate, MARKET),
                tzinfo=market_timezone(MARKET),
            )
            + EOD_PUBLICATION_DELAY
        )
        if local >= due:
            return candidate
    candidate -= dt.timedelta(days=1)
    while not is_trading_day(candidate, market=MARKET):
        candidate -= dt.timedelta(days=1)
    return candidate


async def _coverage(session_date: dt.date) -> tuple[int, int]:
    sm = get_sessionmaker()
    async with sm() as session:
        await bind_tenant_context(session, TENANT_ID)
        ready = (
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
        ) or 0
        covered = (
            await session.scalar(
                select(func.count(func.distinct(DailyBar.code))).where(
                    DailyBar.market == MARKET,
                    DailyBar.date == session_date,
                    DailyBar.code.in_(
                        select(Symbol.code).where(
                            Symbol.market == MARKET,
                            Symbol.is_active.is_(True),
                            Symbol.is_hidden.is_(False),
                            Symbol.data_status == "ready",
                        )
                    ),
                )
            )
        ) or 0
    return ready, covered


async def _evaluate_eod_price_alerts() -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        prices = dict(
            (
                await session.execute(
                    select(QuoteSnapshot.code, QuoteSnapshot.ltp).where(
                        QuoteSnapshot.market == MARKET
                    )
                )
            ).all()
        )
        fired = await check_price_alerts(session, TENANT_ID, MARKET, prices)
        await session.commit()
    return fired


async def run_us_eod_chain(ctx) -> str:
    session_date = most_recent_due_session(dt.datetime.now(dt.UTC))
    if session_date.year not in US_VERIFIED_CALENDAR_YEARS:
        raise RuntimeError(
            f"US exchange calendar is not verified for {session_date.year}; update it before ingestion"
        )
    redis = ctx.get("redis") if ctx else None
    completion_key = _completion_key(session_date)
    if redis is not None and await redis.get(completion_key):
        return f"skipped: {session_date} EOD chain already complete"

    ready, covered = await _coverage(session_date)
    if ready == 0:
        return "skipped: no retail-ready US symbols"
    required = math.ceil(ready * get_settings().us_eod_min_coverage)

    bars = {"bars_upserted": 0}
    if covered < required:
        bars = await collect(MARKET, days=US_DAILY_LOOKBACK_DAYS)
        ready, covered = await _coverage(session_date)
    if covered < required:
        raise RuntimeError(
            f"US EOD coverage below gate for {session_date}: {covered}/{ready}, required {required}"
        )

    eod_snapshot = await publish_us_eod()
    analytics = await compute_all(MARKET)
    levels = await run_levels_agent(MARKET, tenant_id=TENANT_ID)
    volume = await run_eod_volume_agent(MARKET, tenant_id=TENANT_ID)
    factors = await run_factor_agents(MARKET, tenant_id=TENANT_ID)
    market_note = await run_market_update(MARKET, tenant_id=TENANT_ID)
    price_alerts = await _evaluate_eod_price_alerts()
    portfolios = await snapshot_portfolios(MARKET, tenant_id=TENANT_ID)
    buzz = await snapshot_all(MARKET, tenant_id=TENANT_ID)
    if redis is not None:
        await redis.set(completion_key, "1", ex=_COMPLETION_TTL_S)
    log.info(
        "us_eod_complete session=%s coverage=%s/%s bars=%s analytics=%s",
        session_date,
        covered,
        ready,
        bars["bars_upserted"],
        analytics["computed"],
    )
    return (
        f"session={session_date} coverage={covered}/{ready} bars={bars['bars_upserted']} "
        f"eod_snapshot={eod_snapshot} analytics={analytics['computed']} "
        f"levels={levels['published']} volume={volume['published']} "
        f"factors={factors['published']} market={market_note['published']} "
        f"price_alerts={price_alerts} portfolios={portfolios} buzz={buzz}"
    )


async def refresh_us_security_master(ctx) -> str:
    stats = await refresh_security_master(MARKET)
    log.info("us_security_master_complete stats=%s", stats)
    return f"security_master={stats}"


async def pull_finra_short_volume(ctx) -> str:
    """FINRA Reg SHO daily short volume — whole US universe, self-healing catch-up.

    Deliberately never raises: an unpublished file (holiday, early run) or a transient FINRA
    outage is a routine skip, and the next run's catch-up window recovers it silently.
    """
    try:
        stats = await collect_finra_short()
    except Exception:
        log.warning("finra_short_volume run failed; next run will catch up", exc_info=True)
        return "finra_short=failed (will catch up)"
    log.info("finra_short_volume_complete stats=%s", stats)
    return f"finra_short={stats}"


async def run_short_flow_notes(ctx) -> str:
    """Short-flow agent notes from the latest ingested Reg SHO session (skips when no data)."""
    try:
        stats = await run_short_flow_agent(MARKET, tenant_id=TENANT_ID)
    except Exception:
        log.warning("short_flow_agent run failed", exc_info=True)
        return "short_flow=failed"
    return f"short_flow={stats}"


async def run_finra_short_chain(ctx) -> str:
    """Ordered FINRA fetch -> validation/checkpoint -> agent evaluation."""
    result = await pull_finra_short_volume(ctx)
    if "failed" in result:
        return result
    notes = await run_short_flow_notes(ctx)
    return f"{result} {notes}"


async def refresh_restricted_research(ctx) -> str:
    """Maintain high-risk research without feeding agents, Ideas, or coverage gates."""
    try:
        stats = await refresh_restricted_market_data()
    except Exception:
        log.warning("restricted_research refresh failed", exc_info=True)
        return "restricted_research=failed (will retry)"
    return f"restricted_research={stats}"


class WorkerSettings:
    on_startup: ClassVar = startup
    functions: ClassVar = [
        run_us_eod_chain,
        refresh_us_security_master,
        pull_finra_short_volume,
        run_short_flow_notes,
        run_finra_short_chain,
        refresh_restricted_research,
    ]
    cron_jobs: ClassVar = [
        # First attempt 22:45 UTC = 17:45 ET winter / 18:45 ET summer — inside the 1-3h
        # post-close window users actually check, and safely past the provider's 90-minute
        # publication delay in both DST states (the due-time gate skips it if not ready yet).
        # 23:30 and 01:30 are recovery runs; 13:30 verifies the previous session after restarts.
        # Coverage gate + completion key make every run idempotent.
        cron(run_us_eod_chain, hour=22, minute=45, run_at_startup=False),
        cron(run_us_eod_chain, hour={1, 13, 23}, minute=30, run_at_startup=True),
        cron(refresh_us_security_master, weekday="sun", hour=12, minute=0),
        # FINRA publishes the daily file ~18:00 ET; 23:45 UTC = 18:45 EST / 19:45 EDT is past it
        # year-round. Startup run + a multi-session catch-up window make missed evenings heal.
        # One ordered job prevents a note evaluation from racing ahead of the file transaction.
        # It is anchored to the latest ingested session and deduped, so restarts cannot double-post.
        cron(run_finra_short_chain, hour=23, minute=45, run_at_startup=True),
        # A separate bounded job keeps research-only names fresh without making them part of
        # EOD coverage, alerts, screeners, Ideas, market aggregates, or agent publication.
        cron(refresh_restricted_research, hour=23, minute=35, run_at_startup=False),
        cron(refresh_restricted_research, hour=13, minute=35, run_at_startup=False),
    ]
    redis_settings: ClassVar = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name: ClassVar = get_settings().us_ingestion_queue_name
    max_jobs: ClassVar = 2
    job_timeout: ClassVar = 7200
