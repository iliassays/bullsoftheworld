"""Dedicated US EOD scheduler.

The US bootstrap provider is EOD-only, so this worker never fabricates intraday quotes. It uses a
separate Redis queue and a coverage gate before publishing analytics. Reference-only symbols are
onboarded explicitly by the backfill CLI; daily runs touch only retail-ready cohorts.

Run in a UTC process:

    uv run arq ingestion.us_worker.WorkerSettings
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import math
from pathlib import Path
from typing import ClassVar

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import func, select

from bulls.core.config import get_settings
from bulls.core.db import bind_tenant_context, get_sessionmaker, verify_runtime_database_role
from bulls.core.markets import US_VERIFIED_CALENDAR_YEARS
from bulls.core.models import DailyBar, QuoteSnapshot, Symbol
from bulls.market_data.calendar import most_recent_completed_session
from bulls.market_data.providers.us_yahoo import EOD_PUBLICATION_DELAY
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
from ingestion.squeeze_scan import run_squeeze_scan
from ingestion.us_eod_snapshot import collect as publish_us_eod
from ingestion.us_options.pipeline import import_option_sentiment

log = logging.getLogger(__name__)
MARKET = "US"
TENANT_ID = "bullsofwallst"
_COMPLETION_TTL_S = 400 * 24 * 60 * 60
_CHAIN_VERSION = "v2"


async def startup(ctx) -> None:
    await verify_runtime_database_role()


def _completion_key(session_date: dt.date) -> str:
    return f"ingestion:{TENANT_ID}:eod-complete:{_CHAIN_VERSION}:{session_date.isoformat()}"


def most_recent_due_session(now: dt.datetime) -> dt.date:
    """Latest US session whose close plus provider-publication delay has elapsed."""
    return most_recent_completed_session(
        now,
        market=MARKET,
        publication_delay=EOD_PUBLICATION_DELAY,
    )


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
    # Squeeze-taxonomy archive rides after analytics; its failure never breaks the chain.
    try:
        squeeze = await run_squeeze_scan(MARKET)
        log.info("us squeeze scan: %s", squeeze)
    except Exception:
        log.exception("US squeeze scan failed; EOD chain continues")
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


async def pull_finra_short_interest(ctx) -> str:
    """Ingest FINRA bi-monthly consolidated short interest (the open short position).

    Distinct from the daily short-volume job: this is the only source that can support short
    interest, % of shares outstanding, and days-to-cover. A settlement date that FINRA has not
    disseminated yet is reported as pending, never as a failure.
    """
    from ingestion.finra_short_interest import collect as collect_short_interest

    try:
        stats = await collect_short_interest()
    except Exception as exc:
        log.exception("finra_short_interest_failed")
        return f"finra_short_interest failed: {exc}"
    return (
        f"finra_short_interest dates={stats['dates_fetched']} "
        f"pending={stats['dates_pending']} rows={stats['rows_upserted']}"
    )


async def refresh_restricted_research(ctx) -> str:
    """Maintain bounded private research data without feeding public product surfaces."""
    try:
        stats = await refresh_restricted_market_data()
    except Exception:
        log.warning("restricted_research refresh failed", exc_info=True)
        return "restricted_research=failed (will retry)"
    return f"restricted_research={stats}"


def _resolve_options_inbox_file(inbox_dir: str, filename: str) -> Path:
    if not filename or Path(filename).name != filename:
        raise ValueError("filename must be a basename inside US_OPTIONS_INBOX_DIR")
    inbox = Path(inbox_dir).expanduser().resolve()
    path = (inbox / filename).resolve(strict=True)
    if path.parent != inbox:
        raise ValueError("option sentiment input escaped the configured inbox")
    return path


async def import_us_option_sentiment(
    ctx,
    filename: str,
    known_at: str,
    completeness: str,
    source_revision: str,
    delivery_mode: str = "historical",
) -> str:
    """Bounded operator-triggered import. No options vendor job runs on a cron schedule."""

    del ctx
    settings = get_settings()
    if not settings.us_options_phase_a_enabled:
        return "us_options=disabled"
    path = await asyncio.to_thread(
        _resolve_options_inbox_file,
        settings.us_options_inbox_dir,
        filename,
    )
    parsed_known_at = dt.datetime.fromisoformat(known_at.replace("Z", "+00:00"))
    sm = get_sessionmaker()
    async with sm() as session:
        snapshot = await import_option_sentiment(
            session,
            path=path,
            known_at=parsed_known_at,
            completeness=completeness,
            source_revision=source_revision,
            delivery_mode=delivery_mode,
            settings=settings,
        )
        await session.commit()
    return (
        f"us_options={snapshot.status} date={snapshot.trade_date} "
        f"rows={snapshot.row_count} snapshot={snapshot.id}"
    )


class WorkerSettings:
    on_startup: ClassVar = startup
    functions: ClassVar = [
        run_us_eod_chain,
        refresh_us_security_master,
        pull_finra_short_volume,
        run_short_flow_notes,
        run_finra_short_chain,
        pull_finra_short_interest,
        refresh_restricted_research,
        import_us_option_sentiment,
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
        # Short interest is bi-monthly and disseminated ~8 business days after each settlement
        # date, so a daily check is cheap and self-healing: already-stored dates are skipped and
        # an undisseminated date is a no-op until FINRA publishes it. 00:20 UTC keeps it clear of
        # the 23:45 short-volume chain.
        cron(pull_finra_short_interest, hour=0, minute=20, run_at_startup=True),
        # Oldest-first batches continue through the post-close window until Atlas-ready names are
        # current. They stay outside EOD coverage, screeners, Ideas, aggregates, and public agents.
        cron(
            refresh_restricted_research,
            hour={1, 3, 5, 7, 9, 11, 13, 23},
            minute=35,
            run_at_startup=False,
        ),
    ]
    redis_settings: ClassVar = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name: ClassVar = get_settings().us_ingestion_queue_name
    max_jobs: ClassVar = 2
    job_timeout: ClassVar = 7200
