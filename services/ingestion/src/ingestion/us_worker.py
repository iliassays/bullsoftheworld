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
from bulls.core.db import get_sessionmaker
from bulls.core.markets import US_VERIFIED_CALENDAR_YEARS
from bulls.core.models import DailyBar, Symbol
from bulls.market_data.calendar import (
    is_trading_day,
    market_close_on,
    market_timezone,
    to_market_tz,
)
from ingestion.analytics import compute_all
from ingestion.buzz import snapshot_all
from ingestion.history import US_DAILY_LOOKBACK_DAYS, collect
from ingestion.portfolio_snapshot import run as snapshot_portfolios
from ingestion.security_master import collect as refresh_security_master

log = logging.getLogger(__name__)
MARKET = "US"
TENANT_ID = "bullsofwallst"
EOD_PUBLICATION_DELAY = dt.timedelta(minutes=90)
_COMPLETION_TTL_S = 400 * 24 * 60 * 60


def _completion_key(session_date: dt.date) -> str:
    return f"ingestion:{TENANT_ID}:eod-complete:{session_date.isoformat()}"


def most_recent_due_session(now: dt.datetime) -> dt.date:
    """Latest US session whose close plus provider-publication delay has elapsed."""
    local = to_market_tz(now, market=MARKET)
    candidate = local.date()
    if is_trading_day(candidate, market=MARKET):
        due = dt.datetime.combine(
            candidate,
            market_close_on(candidate, MARKET),
            tzinfo=market_timezone(MARKET),
        ) + EOD_PUBLICATION_DELAY
        if local >= due:
            return candidate
    candidate -= dt.timedelta(days=1)
    while not is_trading_day(candidate, market=MARKET):
        candidate -= dt.timedelta(days=1)
    return candidate


async def _coverage(session_date: dt.date) -> tuple[int, int]:
    sm = get_sessionmaker()
    async with sm() as session:
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

    analytics = await compute_all(MARKET)
    portfolios = await snapshot_portfolios(MARKET)
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
        f"analytics={analytics['computed']} portfolios={portfolios} buzz={buzz}"
    )


async def refresh_us_security_master(ctx) -> str:
    stats = await refresh_security_master(MARKET)
    log.info("us_security_master_complete stats=%s", stats)
    return f"security_master={stats}"


class WorkerSettings:
    functions: ClassVar = [run_us_eod_chain, refresh_us_security_master]
    cron_jobs: ClassVar = [
        # 23:30 UTC is 19:30 ET in summer / 18:30 ET in winter. 01:30 is a recovery run;
        # 13:30 verifies the previous session after restarts. Coverage makes all runs idempotent.
        cron(run_us_eod_chain, hour={1, 13, 23}, minute=30, run_at_startup=True),
        cron(refresh_us_security_master, weekday="sun", hour=12, minute=0),
    ]
    redis_settings: ClassVar = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name: ClassVar = get_settings().us_ingestion_queue_name
    max_jobs: ClassVar = 2
    job_timeout: ClassVar = 7200
