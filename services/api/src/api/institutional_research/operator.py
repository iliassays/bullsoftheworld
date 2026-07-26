"""Explicit-account operator workflow for configuring the Atlas lifecycle."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select

from api.institutional_research.audit import record_research_audit_event
from api.institutional_research.lifecycle import upsert_automation_policy
from api.institutional_research.portfolio import (
    create_shadow_portfolio,
    reconcile_shadow_portfolios,
)
from api.institutional_research.schemas import (
    AutomationPolicyUpdate,
    BacktestRequest,
    CreateShadowPortfolioRequest,
)
from api.institutional_research.workflow import execute_backtest
from api.institutional_research.workspaces import bootstrap_personal_workspace
from api.queue import enqueue_research_lifecycle
from api.research_access import bind_research_tenant_context
from bulls.analytics.research_strategy import STRATEGIES
from bulls.core.db import bind_tenant_context, get_sessionmaker
from bulls.core.models import (
    DailyBar,
    ResearchShadowPortfolio,
    ResearchShadowSnapshot,
    ResearchStrategyTrial,
    ResearchWorkspace,
    User,
)
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


@dataclass(frozen=True, slots=True)
class HistoricalReplayOperatorRequest:
    tenant: str
    handle: str
    strategy_key: str
    initial_capital: float
    history_days: int = 31
    universe_limit: int = 25
    cap_tier: str | None = None
    apply: bool = False


@dataclass(frozen=True, slots=True)
class ForwardShadowOperatorRequest:
    tenant: str
    handle: str
    strategy_key: str
    initial_capital: float
    universe_limit: int = 500
    cap_tier: str | None = None
    replace_empty: bool = False
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


async def seed_historical_replay(
    request: HistoricalReplayOperatorRequest,
) -> dict[str, object]:
    """Create one labeled replay book, then advance it to the latest completed session.

    Replayed snapshots are useful for UI archives and engine diagnostics, but their dates precede
    ``forward_evidence_started_on`` and therefore cannot satisfy forward promotion gates.
    """

    if not request.apply:
        raise RuntimeError("Refusing to seed historical replay without --apply")
    if request.history_days < 7 or request.history_days > 366:
        raise ValueError("history_days must be between 7 and 366")

    registry = TenantRegistry.from_dir(_TENANTS_DIR, default="bullsofdhaka")
    tenant = registry.get(request.tenant)
    if tenant is None:
        raise RuntimeError(f"Unknown tenant: {request.tenant}")
    strategy = STRATEGIES[request.strategy_key]
    if strategy.market != tenant.market:
        raise RuntimeError(
            f"Strategy {request.strategy_key} is registered for {strategy.market}, "
            f"not {tenant.market}"
        )

    async with get_sessionmaker()() as session:
        await bind_tenant_context(session, tenant.name)
        user = await session.scalar(
            select(User).where(User.tenant_id == tenant.name, User.handle == request.handle)
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

        existing = await session.scalar(
            select(ResearchShadowPortfolio).where(
                ResearchShadowPortfolio.workspace_id == workspace.id,
                ResearchShadowPortfolio.organization_id == workspace.organization_id,
                ResearchShadowPortfolio.tenant_id == workspace.tenant_id,
                ResearchShadowPortfolio.market == workspace.market,
                ResearchShadowPortfolio.strategy_key == request.strategy_key,
                ResearchShadowPortfolio.status.in_(("active", "paused")),
            )
        )
        if existing is not None:
            portfolios = await reconcile_shadow_portfolios(session, workspace=workspace)
            await session.commit()
            matched = next(item for item in portfolios if item.id == existing.id)
            return {
                "status": "existing",
                "tenant": tenant.name,
                "market": tenant.market,
                "handle": user.handle,
                "workspace_id": str(workspace.id),
                "portfolio_id": str(existing.id),
                "inception_date": matched.inception_date.isoformat(),
                "last_evaluated_on": (
                    matched.last_evaluated_on.isoformat() if matched.last_evaluated_on else None
                ),
                "snapshots": len(matched.snapshots),
            }

        latest_date = await session.scalar(
            select(func.max(DailyBar.date)).where(DailyBar.market == tenant.market)
        )
        if latest_date is None:
            raise RuntimeError(f"No completed {tenant.market} bars are available")
        seed_cutoff = latest_date - dt.timedelta(days=request.history_days)
        seed_date = await session.scalar(
            select(func.max(DailyBar.date)).where(
                DailyBar.market == tenant.market,
                DailyBar.date <= seed_cutoff,
            )
        )
        if seed_date is None:
            raise RuntimeError("No completed session exists before the requested replay window")

        backtest = await execute_backtest(
            session,
            workspace=workspace,
            user_id=user.id,
            request=BacktestRequest(
                idempotency_key=(
                    f"history-seed:{request.strategy_key}:{seed_date.isoformat()}:"
                    f"{request.cap_tier or 'all'}:{request.universe_limit}"
                ),
                strategy_key=request.strategy_key,
                end_date=seed_date,
                cap_tier=request.cap_tier,
                universe_limit=request.universe_limit,
                initial_capital=request.initial_capital,
            ),
        )
        created = await create_shadow_portfolio(
            session,
            workspace=workspace,
            user_id=user.id,
            request=CreateShadowPortfolioRequest(
                source_run_id=backtest.id,
                name=f"Atlas {request.strategy_key} replay + forward book",
            ),
            forward_evidence_started_on=latest_date + dt.timedelta(days=1),
            history_mode="retroactive_replay_then_forward",
        )
        portfolio = await session.get(ResearchShadowPortfolio, created.id)
        if portfolio is None:
            raise RuntimeError("Created replay book could not be reloaded")
        portfolio.configuration = {
            **portfolio.configuration,
            "managed_by": "atlas_lifecycle",
            "historical_replay_requested_days": request.history_days,
            "historical_replay_seed_date": seed_date.isoformat(),
        }
        await session.flush()
        portfolios = await reconcile_shadow_portfolios(session, workspace=workspace)
        matched = next(item for item in portfolios if item.id == created.id)
        record_research_audit_event(
            session,
            workspace=workspace,
            actor_user_id=user.id,
            event_type="research_historical_replay_seeded",
            resource_type="research_shadow_portfolio",
            resource_id=str(created.id),
            attributes={
                "seed_date": seed_date.isoformat(),
                "latest_date": latest_date.isoformat(),
                "history_days": request.history_days,
                "forward_evidence_started_on": (latest_date + dt.timedelta(days=1)).isoformat(),
            },
        )
        await session.commit()
        return {
            "status": "created",
            "tenant": tenant.name,
            "market": tenant.market,
            "handle": user.handle,
            "workspace_id": str(workspace.id),
            "portfolio_id": str(created.id),
            "seed_date": seed_date.isoformat(),
            "last_evaluated_on": (
                matched.last_evaluated_on.isoformat() if matched.last_evaluated_on else None
            ),
            "snapshots": len(matched.snapshots),
            "forward_evidence_started_on": (latest_date + dt.timedelta(days=1)).isoformat(),
        }


async def seed_forward_shadow(request: ForwardShadowOperatorRequest) -> dict[str, object]:
    """Register a diagnostic backtest and start a cash-only forward shadow book."""

    if not request.apply:
        raise RuntimeError("Refusing to seed a forward shadow book without --apply")
    registry = TenantRegistry.from_dir(_TENANTS_DIR, default="bullsofdhaka")
    tenant = registry.get(request.tenant)
    if tenant is None:
        raise RuntimeError(f"Unknown tenant: {request.tenant}")
    strategy = STRATEGIES[request.strategy_key]
    if strategy.market != tenant.market:
        raise RuntimeError(
            f"Strategy {request.strategy_key} is registered for {strategy.market}, "
            f"not {tenant.market}"
        )

    async with get_sessionmaker()() as session:
        await bind_tenant_context(session, tenant.name)
        user = await session.scalar(
            select(User).where(User.tenant_id == tenant.name, User.handle == request.handle)
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

        existing = await session.scalar(
            select(ResearchShadowPortfolio).where(
                ResearchShadowPortfolio.workspace_id == workspace.id,
                ResearchShadowPortfolio.organization_id == workspace.organization_id,
                ResearchShadowPortfolio.tenant_id == workspace.tenant_id,
                ResearchShadowPortfolio.market == workspace.market,
                ResearchShadowPortfolio.strategy_key == request.strategy_key,
                ResearchShadowPortfolio.status.in_(("active", "paused")),
            )
        )
        if existing is not None and request.replace_empty:
            snapshot = await session.scalar(
                select(ResearchShadowSnapshot)
                .where(ResearchShadowSnapshot.portfolio_id == existing.id)
                .order_by(ResearchShadowSnapshot.session_number.desc())
                .limit(1)
            )
            if (
                snapshot is None
                or snapshot.session_number != 0
                or snapshot.target_weights
                or snapshot.positions
                or snapshot.trades
            ):
                raise RuntimeError(
                    "Refusing to replace a shadow book after it produced targets, positions, "
                    "trades, or forward sessions"
                )
            trial = await session.scalar(
                select(ResearchStrategyTrial).where(
                    ResearchStrategyTrial.source_run_id == existing.source_run_id,
                    ResearchStrategyTrial.workspace_id == workspace.id,
                    ResearchStrategyTrial.organization_id == workspace.organization_id,
                    ResearchStrategyTrial.tenant_id == workspace.tenant_id,
                    ResearchStrategyTrial.market == workspace.market,
                )
            )
            existing.status = "archived"
            if trial is not None:
                trial.status = "retired"
            record_research_audit_event(
                session,
                workspace=workspace,
                actor_user_id=user.id,
                event_type="research_empty_shadow_archived",
                resource_type="research_shadow_portfolio",
                resource_id=str(existing.id),
                attributes={
                    "strategy_key": request.strategy_key,
                    "source_run_id": str(existing.source_run_id),
                    "trial_id": str(trial.id) if trial is not None else None,
                    "reason": "Pre-forward adapter correction; no target, fill, or evidence session existed.",
                },
            )
            await session.flush()
            existing = None
        if existing is not None:
            portfolios = await reconcile_shadow_portfolios(session, workspace=workspace)
            await session.commit()
            matched = next(item for item in portfolios if item.id == existing.id)
            return {
                "status": "existing",
                "portfolio_id": str(existing.id),
                "last_evaluated_on": (
                    matched.last_evaluated_on.isoformat() if matched.last_evaluated_on else None
                ),
                "snapshots": len(matched.snapshots),
            }

        latest_date = await session.scalar(
            select(func.max(DailyBar.date)).where(DailyBar.market == tenant.market)
        )
        if latest_date is None:
            raise RuntimeError(f"No completed {tenant.market} bars are available")
        backtest = await execute_backtest(
            session,
            workspace=workspace,
            user_id=user.id,
            request=BacktestRequest(
                idempotency_key=(
                    f"forward-seed:{request.strategy_key}:{strategy.methodology_version}:"
                    f"{latest_date.isoformat()}:"
                    f"{request.cap_tier or 'all'}:{request.universe_limit}"
                ),
                strategy_key=request.strategy_key,
                end_date=latest_date,
                cap_tier=request.cap_tier,
                universe_limit=request.universe_limit,
                initial_capital=request.initial_capital,
            ),
        )
        forward_start = latest_date + dt.timedelta(days=1)
        created = await create_shadow_portfolio(
            session,
            workspace=workspace,
            user_id=user.id,
            request=CreateShadowPortfolioRequest(
                source_run_id=backtest.id,
                name=(
                    f"Atlas {request.strategy_key} {strategy.methodology_version} "
                    "forward diagnostic"
                ),
            ),
            forward_evidence_started_on=forward_start,
            history_mode="locked_forward_only",
        )
        portfolio = await session.get(ResearchShadowPortfolio, created.id)
        if portfolio is None:
            raise RuntimeError("Created forward book could not be reloaded")
        portfolio.configuration = {
            **portfolio.configuration,
            "managed_by": "registered_forward_experiment",
        }
        record_research_audit_event(
            session,
            workspace=workspace,
            actor_user_id=user.id,
            event_type="research_forward_shadow_seeded",
            resource_type="research_shadow_portfolio",
            resource_id=str(created.id),
            attributes={
                "strategy_key": request.strategy_key,
                "source_run_id": str(backtest.id),
                "source_validation_status": created.configuration.get("source_validation_status"),
                "forward_evidence_started_on": forward_start.isoformat(),
            },
        )
        await session.commit()
        return {
            "status": "created",
            "tenant": tenant.name,
            "market": tenant.market,
            "handle": user.handle,
            "workspace_id": str(workspace.id),
            "source_run_id": str(backtest.id),
            "portfolio_id": str(created.id),
            "inception_date": created.inception_date.isoformat(),
            "forward_evidence_started_on": forward_start.isoformat(),
            "source_validation_status": created.configuration.get("source_validation_status"),
            "initial_targets": created.snapshots[0].target_weights,
        }


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate one exact Atlas account")
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure = subparsers.add_parser("configure", help="Configure lifecycle automation")
    configure.add_argument("--tenant", required=True)
    configure.add_argument("--handle", required=True)
    configure.add_argument("--strategy", required=True)
    configure.add_argument("--initial-capital", type=float, required=True)
    configure.add_argument("--queue-limit", type=int, default=20)
    configure.add_argument("--research-limit", type=int, default=5)
    configure.add_argument("--universe-limit", type=int, default=25)
    configure.add_argument("--cap-tier")
    configure.add_argument("--enable", action="store_true")
    configure.add_argument("--dispatch-now", action="store_true")
    configure.add_argument("--apply", action="store_true")

    replay = subparsers.add_parser(
        "replay", help="Seed labeled history then begin forward evidence"
    )
    replay.add_argument("--tenant", required=True)
    replay.add_argument("--handle", required=True)
    replay.add_argument("--strategy", required=True)
    replay.add_argument("--initial-capital", type=float, required=True)
    replay.add_argument("--history-days", type=int, default=31)
    replay.add_argument("--universe-limit", type=int, default=25)
    replay.add_argument("--cap-tier")
    replay.add_argument("--apply", action="store_true")
    forward = subparsers.add_parser(
        "forward", help="Register a backtest and start a cash-only forward shadow book"
    )
    forward.add_argument("--tenant", required=True)
    forward.add_argument("--handle", required=True)
    forward.add_argument("--strategy", required=True)
    forward.add_argument("--initial-capital", type=float, required=True)
    forward.add_argument("--universe-limit", type=int, default=500)
    forward.add_argument("--cap-tier")
    forward.add_argument("--replace-empty", action="store_true")
    forward.add_argument("--apply", action="store_true")
    return parser


async def _main() -> None:
    arguments = _argument_parser().parse_args()
    if arguments.command == "configure":
        result = await configure_lifecycle(
            LifecycleOperatorRequest(
                tenant=arguments.tenant,
                handle=arguments.handle,
                strategy_key=arguments.strategy,
                initial_capital=arguments.initial_capital,
                queue_limit=arguments.queue_limit,
                research_limit=arguments.research_limit,
                universe_limit=arguments.universe_limit,
                cap_tier=arguments.cap_tier,
                enable=arguments.enable,
                dispatch_now=arguments.dispatch_now,
                apply=arguments.apply,
            )
        )
    elif arguments.command == "replay":
        result = await seed_historical_replay(
            HistoricalReplayOperatorRequest(
                tenant=arguments.tenant,
                handle=arguments.handle,
                strategy_key=arguments.strategy,
                initial_capital=arguments.initial_capital,
                history_days=arguments.history_days,
                universe_limit=arguments.universe_limit,
                cap_tier=arguments.cap_tier,
                apply=arguments.apply,
            )
        )
    else:
        result = await seed_forward_shadow(
            ForwardShadowOperatorRequest(
                tenant=arguments.tenant,
                handle=arguments.handle,
                strategy_key=arguments.strategy,
                initial_capital=arguments.initial_capital,
                universe_limit=arguments.universe_limit,
                cap_tier=arguments.cap_tier,
                replace_empty=arguments.replace_empty,
                apply=arguments.apply,
            )
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(_main())
