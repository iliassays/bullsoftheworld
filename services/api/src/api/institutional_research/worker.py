"""Dedicated worker for tenant-bound Atlas lifecycle jobs."""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import ClassVar

from arq.connections import RedisSettings
from sqlalchemy import select, text

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
    ResearchWorkspace,
    TickerAnalytics,
)

log = logging.getLogger(__name__)


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
            if expected_session is not None and (
                latest_bar is None
                or latest_bar < expected_session
                or latest_analytics is None
                or latest_analytics < expected_session
            ):
                policy.last_run_status = "failed"
                policy.last_completed_at = dt.datetime.now(dt.UTC)
                policy.last_error = (
                    f"Research preflight refused stale inputs: expected {expected_session}, "
                    f"latest bar {latest_bar}, latest analytics {latest_analytics}."
                )
                policy.next_run_at = (
                    dt.datetime.now(dt.UTC) + dt.timedelta(minutes=30)
                    if policy.enabled
                    else None
                )
                await session.commit()
                await _schedule_next(ctx, policy)
                return "data-not-ready"
            run = await execute_research_lifecycle(
                session,
                workspace=workspace,
                policy=policy,
                trigger_key=trigger_key,
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
    on_startup: ClassVar = startup
    redis_settings: ClassVar = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name: ClassVar = get_settings().research_lifecycle_queue_name
    max_jobs: ClassVar = 1
    max_tries: ClassVar = 3
    job_timeout: ClassVar = 7200
