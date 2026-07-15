"""Explicit-account operator workflow for configuring the Atlas lifecycle."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from api.institutional_research.audit import record_research_audit_event
from api.institutional_research.lifecycle import upsert_automation_policy
from api.institutional_research.schemas import AutomationPolicyUpdate
from api.institutional_research.workspaces import bootstrap_personal_workspace
from api.queue import enqueue_research_lifecycle
from api.research_access import bind_research_tenant_context
from bulls.analytics.research_strategy import STRATEGIES
from bulls.core.db import bind_tenant_context, get_sessionmaker
from bulls.core.models import ResearchWorkspace, User
from bulls.core.tenancy import TenantRegistry

_TENANTS_DIR = Path(__file__).resolve().parents[5] / "tenants"


@dataclass(frozen=True, slots=True)
class LifecycleOperatorRequest:
    tenant: str
    handle: str
    strategy_key: str
    initial_capital: float
    queue_limit: int = 20
    research_limit: int = 5
    universe_limit: int = 25
    cap_tier: str | None = None
    enable: bool = False
    dispatch_now: bool = False
    apply: bool = False


async def configure_lifecycle(request: LifecycleOperatorRequest) -> dict[str, object]:
    """Configure one user's policy and enqueue only that exact RLS identity."""

    if not request.apply:
        raise RuntimeError("Refusing to mutate lifecycle state without --apply")

    registry = TenantRegistry.from_dir(_TENANTS_DIR, default="bullsofdhaka")
    tenant = registry.get(request.tenant)
    if tenant is None:
        raise RuntimeError(f"Unknown tenant: {request.tenant}")
    if tenant.research_access != "authenticated":
        raise RuntimeError(f"Atlas access is not enabled for {tenant.name}")

    strategy = STRATEGIES[request.strategy_key]
    if strategy.market != tenant.market:
        raise RuntimeError(
            f"Strategy {request.strategy_key} is registered for {strategy.market}, "
            f"not {tenant.market}"
        )

    async with get_sessionmaker()() as session:
        await bind_tenant_context(session, tenant.name)
        user = await session.scalar(
            select(User).where(
                User.tenant_id == tenant.name,
                User.handle == request.handle,
            )
        )
        if user is None:
            raise RuntimeError(f"Account {request.handle!r} not found in {tenant.name}")

        await bind_research_tenant_context(
            session,
            tenant_id=tenant.name,
            market=tenant.market,
            user_id=user.id,
        )
        workspace_out = await bootstrap_personal_workspace(session, tenant=tenant, user=user)
        workspace = await session.scalar(
            select(ResearchWorkspace).where(
                ResearchWorkspace.id == workspace_out.id,
                ResearchWorkspace.tenant_id == tenant.name,
                ResearchWorkspace.market == tenant.market,
            )
        )
        if workspace is None:
            raise RuntimeError("The RLS-bound workspace could not be reloaded")

        policy = await upsert_automation_policy(
            session,
            workspace=workspace,
            user_id=user.id,
            payload=AutomationPolicyUpdate(
                enabled=request.enable,
                queue_limit=request.queue_limit,
                research_limit=request.research_limit,
                cap_tier=request.cap_tier,
                strategy_key=request.strategy_key,
                universe_limit=request.universe_limit,
                initial_capital=request.initial_capital,
            ),
        )
        record_research_audit_event(
            session,
            workspace=workspace,
            actor_user_id=user.id,
            event_type="research_automation_configured",
            resource_type="research_automation_policy",
            resource_id=str(policy.id),
            attributes={
                "source": "operator_command",
                "enabled": policy.enabled,
                "strategy_key": policy.strategy_key,
                "cap_tier": policy.cap_tier,
            },
        )

        should_enqueue = request.dispatch_now or request.enable
        scheduled = request.enable and not request.dispatch_now
        trigger_kind = "operator" if request.dispatch_now else "scheduled"
        trigger_key = f"{trigger_kind}:{uuid.uuid4()}"
        job_id = f"atlas:lifecycle:{policy.id}:{trigger_kind}:{uuid.uuid4().hex}"
        if should_enqueue:
            policy.last_run_status = "queued"
            policy.last_error = None
            record_research_audit_event(
                session,
                workspace=workspace,
                actor_user_id=user.id,
                event_type="research_lifecycle_dispatched",
                resource_type="research_automation_policy",
                resource_id=str(policy.id),
                attributes={
                    "source": "operator_command",
                    "job_id": job_id,
                    "trigger": trigger_kind,
                },
            )
        await session.commit()

        accepted = False
        if should_enqueue:
            try:
                accepted = await enqueue_research_lifecycle(
                    policy_id=str(policy.id),
                    workspace_id=str(policy.workspace_id),
                    tenant_id=policy.tenant_id,
                    market=policy.market,
                    user_id=policy.requested_by_user_id,
                    trigger_key=trigger_key,
                    job_id=job_id,
                    scheduled=scheduled,
                    defer_until=policy.next_run_at if scheduled else None,
                )
            except Exception as exc:
                await bind_research_tenant_context(
                    session,
                    tenant_id=tenant.name,
                    market=tenant.market,
                    user_id=user.id,
                )
                policy.last_run_status = "failed"
                policy.last_error = f"Lifecycle enqueue failed: {exc}"[:2000]
                await session.commit()
                raise

        return {
            "tenant": policy.tenant_id,
            "market": policy.market,
            "handle": user.handle,
            "workspace_id": str(policy.workspace_id),
            "policy_id": str(policy.id),
            "enabled": policy.enabled,
            "next_run_at": policy.next_run_at.isoformat() if policy.next_run_at else None,
            "job_id": job_id if should_enqueue else None,
            "accepted": accepted,
        }
