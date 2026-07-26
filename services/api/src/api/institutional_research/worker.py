"""Dedicated worker for tenant-bound Atlas lifecycle jobs."""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import func, select, text

from api.institutional_research.catalysts import collect_catalyst_events
from api.institutional_research.lifecycle import (
    execute_research_lifecycle,
    expected_lifecycle_session,
    next_lifecycle_run_at,
)
from api.research_access import bind_research_tenant_context
from bulls.core.config import get_settings
from bulls.core.db import get_sessionmaker, verify_runtime_database_role
from bulls.core.models import (
    DailyBar,
    ResearchAutomationPolicy,
    ResearchShadowPortfolio,
    ResearchWorkspace,
    SqueezeDailyState,
    TickerAnalytics,
)
from bulls.core.tenancy import Tenant, TenantRegistry

log = logging.getLogger(__name__)

_TENANTS_DIR = Path(__file__).resolve().parents[5] / "tenants"
# System-triggered collection; catalyst rows are tenant-shared, so the RLS user id does not gate.
_SYSTEM_USER_ID = 0
_DATA_READINESS_RETRY = dt.timedelta(minutes=15)
_DSE_SQUEEZE_STRATEGIES = {
    "dse_compression_breakout_20d_v1",
    "dse_selective_compression_v1",
}


def lifecycle_freshness_error(
    *,
    expected_session: dt.date,
    latest_bar: dt.date | None,
    latest_analytics: dt.date | None,
    squeeze_archive_required: bool = False,
    latest_squeeze_archive: dt.date | None = None,
) -> str | None:
    """Return the exact point-in-time dependency that is not ready for this lifecycle."""

    stale = [
        label
        for label, observed in (
            ("bar", latest_bar),
            ("analytics", latest_analytics),
            *(
                (("DSE squeeze archive", latest_squeeze_archive),)
                if squeeze_archive_required
                else ()
            ),
        )
        if observed is None or observed < expected_session
    ]
    if not stale:
        return None
    return (
        f"Research preflight refused stale inputs: expected {expected_session}, "
        f"latest bar {latest_bar}, latest analytics {latest_analytics}, "
        f"latest DSE squeeze archive {latest_squeeze_archive}; "
        f"waiting for {', '.join(stale)}."
    )


def lifecycle_execution_trigger(
    trigger_key: str,
    *,
    scheduled: bool,
    market: str,
    latest_bar: dt.date,
    latest_analytics: dt.date,
) -> str:
    """Collapse all automatic attempts for one completed market session into one durable run.

    Operators retain unique trigger keys so an explicit manual rerun remains possible. Scheduled
    attempts use the oldest fully available input date, preventing an early attempt, a retry, and
    a previously deferred fallback from advancing the lifecycle more than once.
    """

    if not scheduled:
        return trigger_key
    completed_session = min(latest_bar, latest_analytics)
    return f"session:{market}:{completed_session.isoformat()}"


def research_collection_targets(
    tenants: Iterable[Tenant],
    *,
    market: str | None = None,
) -> list[tuple[str, str]]:
    """(tenant, market) pairs whose Atlas product is open; closed tenants are never scanned."""
    return [
        (tenant.name, tenant.market)
        for tenant in tenants
        if tenant.research_access == "authenticated" and (market is None or tenant.market == market)
    ]


async def collect_market_catalysts(ctx, market: str) -> None:
    """Refresh one market only; the DSE and US schedules must never rescan each other."""
    registry = TenantRegistry.from_dir(_TENANTS_DIR, default=get_settings().default_tenant)
    for tenant_id, tenant_market in research_collection_targets(registry.all(), market=market):
        try:
            result = await collect_catalyst_events(
                tenant_id=tenant_id, market=tenant_market, user_id=_SYSTEM_USER_ID
            )
            log.info("catalyst collection: %s", result)
        except Exception:
            log.exception("catalyst collection failed for %s/%s", tenant_id, tenant_market)


async def collect_dse_catalysts(ctx) -> None:
    await collect_market_catalysts(ctx, "DSE")


async def collect_us_catalysts(ctx) -> None:
    await collect_market_catalysts(ctx, "US")


async def _schedule_next(ctx, policy: ResearchAutomationPolicy) -> None:
    if not policy.enabled or policy.next_run_at is None:
        return
    slot = policy.next_run_at.astimezone(dt.UTC)
    job_id = f"atlas:lifecycle:{policy.id}:{slot.strftime('%Y%m%dT%H%M')}"
    await ctx["redis"].enqueue_job(
        "run_research_lifecycle",
        str(policy.id),
        str(policy.workspace_id),
        policy.tenant_id,
        policy.market,
        policy.requested_by_user_id,
        f"scheduled:{slot.isoformat()}",
        True,
        _job_id=job_id,
        _defer_until=slot,
    )


async def run_research_lifecycle(
    ctx,
    policy_id: str,
    workspace_id: str,
    tenant_id: str,
    market: str,
    user_id: int,
    trigger_key: str,
    scheduled: bool,
) -> str:
    """Execute one policy only after binding its explicit tenant, market, and user context."""

    parsed_policy_id = uuid.UUID(policy_id)
    parsed_workspace_id = uuid.UUID(workspace_id)
    sm = get_sessionmaker()
    try:
        async with sm() as session:
            await bind_research_tenant_context(
                session, tenant_id=tenant_id, market=market, user_id=user_id
            )
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
                {"identity": f"atlas-lifecycle:{policy_id}"},
            )
            policy = await session.scalar(
                select(ResearchAutomationPolicy).where(
                    ResearchAutomationPolicy.id == parsed_policy_id,
                    ResearchAutomationPolicy.workspace_id == parsed_workspace_id,
                    ResearchAutomationPolicy.tenant_id == tenant_id,
                    ResearchAutomationPolicy.market == market,
                    ResearchAutomationPolicy.requested_by_user_id == user_id,
                )
            )
            workspace = await session.scalar(
                select(ResearchWorkspace).where(
                    ResearchWorkspace.id == parsed_workspace_id,
                    ResearchWorkspace.tenant_id == tenant_id,
                    ResearchWorkspace.market == market,
                    ResearchWorkspace.status == "active",
                )
            )
            if policy is None or workspace is None:
                return "policy-or-workspace-unavailable"
            if scheduled and not policy.enabled:
                return "automation-disabled"

            policy.last_run_status = "running"
            policy.last_started_at = dt.datetime.now(dt.UTC)
            policy.last_error = None
            await session.flush()
            expected_session = expected_lifecycle_session(market)
            latest_bar = await session.scalar(
                select(DailyBar.date)
                .where(DailyBar.market == market)
                .order_by(DailyBar.date.desc())
                .limit(1)
            )
            latest_analytics = await session.scalar(
                select(TickerAnalytics.as_of_date)
                .where(TickerAnalytics.market == market)
                .order_by(TickerAnalytics.as_of_date.desc())
                .limit(1)
            )
            squeeze_archive_required = False
            latest_squeeze_archive = None
            if market == "DSE":
                squeeze_archive_required = (
                    await session.scalar(
                        select(ResearchShadowPortfolio.id)
                        .where(
                            ResearchShadowPortfolio.workspace_id == workspace.id,
                            ResearchShadowPortfolio.organization_id == workspace.organization_id,
                            ResearchShadowPortfolio.tenant_id == tenant_id,
                            ResearchShadowPortfolio.market == "DSE",
                            ResearchShadowPortfolio.strategy_key.in_(_DSE_SQUEEZE_STRATEGIES),
                            ResearchShadowPortfolio.status == "active",
                        )
                        .limit(1)
                    )
                    is not None
                )
                if squeeze_archive_required:
                    latest_squeeze_archive = await session.scalar(
                        select(func.max(SqueezeDailyState.as_of_date)).where(
                            SqueezeDailyState.market == "DSE",
                            SqueezeDailyState.family == "compression_breakout",
                            SqueezeDailyState.methodology_version == "squeeze-monitor-v3",
                            SqueezeDailyState.evidence_mode == "forward",
                        )
                    )
            freshness_error = (
                lifecycle_freshness_error(
                    expected_session=expected_session,
                    latest_bar=latest_bar,
                    latest_analytics=latest_analytics,
                    squeeze_archive_required=squeeze_archive_required,
                    latest_squeeze_archive=latest_squeeze_archive,
                )
                if expected_session is not None
                else None
            )
            if freshness_error is not None:
                policy.last_run_status = "failed"
                policy.last_completed_at = dt.datetime.now(dt.UTC)
                policy.last_error = freshness_error
                policy.next_run_at = (
                    dt.datetime.now(dt.UTC) + _DATA_READINESS_RETRY if policy.enabled else None
                )
                await session.commit()
                await _schedule_next(ctx, policy)
                return "data-not-ready"
            if latest_bar is None or latest_analytics is None:
                # ``expected_session`` can be None before the first configured market slot. A
                # manually scheduled policy still must never execute without both input families.
                policy.last_run_status = "failed"
                policy.last_completed_at = dt.datetime.now(dt.UTC)
                policy.last_error = (
                    "Research preflight refused missing bars or analytics: "
                    f"latest bar {latest_bar}, latest analytics {latest_analytics}."
                )
                policy.next_run_at = (
                    dt.datetime.now(dt.UTC) + _DATA_READINESS_RETRY if policy.enabled else None
                )
                await session.commit()
                await _schedule_next(ctx, policy)
                return "data-not-ready"
            execution_trigger = lifecycle_execution_trigger(
                trigger_key,
                scheduled=scheduled,
                market=market,
                latest_bar=latest_bar,
                latest_analytics=latest_analytics,
            )
            run = await execute_research_lifecycle(
                session,
                workspace=workspace,
                policy=policy,
                trigger_key=execution_trigger,
            )
            policy.last_run_status = run.status
            policy.last_completed_at = dt.datetime.now(dt.UTC)
            policy.next_run_at = next_lifecycle_run_at(market) if policy.enabled else None
            await session.commit()
            await _schedule_next(ctx, policy)
            return f"lifecycle={run.id} status={run.status} market={market}"
    except Exception as exc:
        log.exception("Atlas lifecycle failed policy=%s market=%s", policy_id, market)
        async with sm() as failure_session:
            await bind_research_tenant_context(
                failure_session, tenant_id=tenant_id, market=market, user_id=user_id
            )
            policy = await failure_session.scalar(
                select(ResearchAutomationPolicy).where(
                    ResearchAutomationPolicy.id == parsed_policy_id,
                    ResearchAutomationPolicy.workspace_id == parsed_workspace_id,
                    ResearchAutomationPolicy.tenant_id == tenant_id,
                    ResearchAutomationPolicy.market == market,
                    ResearchAutomationPolicy.requested_by_user_id == user_id,
                )
            )
            if policy is not None:
                policy.last_run_status = "failed"
                policy.last_completed_at = dt.datetime.now(dt.UTC)
                policy.last_error = str(exc)[:2000]
                policy.next_run_at = next_lifecycle_run_at(market) if policy.enabled else None
                await failure_session.commit()
                await _schedule_next(ctx, policy)
        raise


async def startup(ctx) -> None:
    await verify_runtime_database_role()


class WorkerSettings:
    functions: ClassVar = [run_research_lifecycle]
    # 14:10 UTC follows the DSE EOD chain (ends 13:50); 22:30 UTC follows the US close and the
    # bulk of same-day EDGAR acceptance. Each job is market-specific.
    cron_jobs: ClassVar = [
        cron(collect_dse_catalysts, hour=14, minute=10, name="catalysts_post_dse"),
        cron(collect_us_catalysts, hour=22, minute=30, name="catalysts_post_us"),
    ]
    on_startup: ClassVar = startup
    redis_settings: ClassVar = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name: ClassVar = get_settings().research_lifecycle_queue_name
    max_jobs: ClassVar = 1
    max_tries: ClassVar = 3
    job_timeout: ClassVar = 7200
