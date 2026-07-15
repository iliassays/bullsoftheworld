"""Durable Atlas lifecycle coordination for one explicitly bound workspace."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.institutional_research.portfolio import (
    create_shadow_portfolio,
    reconcile_shadow_portfolios,
    refresh_outcome_observations,
)
from api.institutional_research.queue import build_research_queue
from api.institutional_research.schemas import (
    AutomationPolicyOut,
    AutomationPolicyUpdate,
    BacktestRequest,
    CreateShadowPortfolioRequest,
    ResearchRunOut,
)
from api.institutional_research.workflow import (
    _add_step,
    _existing_run,
    _new_run,
    _stable_hash,
    execute_backtest,
    execute_company_research,
    load_research_run,
)
from bulls.analytics.research_strategy import STRATEGIES
from bulls.core.models import (
    DailyBar,
    ResearchAutomationPolicy,
    ResearchShadowPortfolio,
    ResearchWorkspace,
)
from bulls.market_data.calendar import is_trading_day, market_close_on, market_timezone

LIFECYCLE_VERSION = "atlas-lifecycle-v1"
_POST_CLOSE_DELAYS = {
    "DSE": dt.timedelta(hours=5),
    "US": dt.timedelta(hours=3, minutes=30),
}


def automation_policy_out(policy: ResearchAutomationPolicy) -> AutomationPolicyOut:
    return AutomationPolicyOut(
        id=policy.id,
        workspace_id=policy.workspace_id,
        tenant_id=policy.tenant_id,
        market=policy.market,
        enabled=policy.enabled,
        queue_limit=policy.queue_limit,
        research_limit=policy.research_limit,
        cap_tier=policy.cap_tier,
        strategy_key=policy.strategy_key,
        universe_limit=policy.universe_limit,
        initial_capital=float(policy.initial_capital),
        next_run_at=policy.next_run_at,
        last_started_at=policy.last_started_at,
        last_completed_at=policy.last_completed_at,
        last_run_status=policy.last_run_status,
        last_error=policy.last_error,
    )


async def get_automation_policy(
    session: AsyncSession, *, workspace: ResearchWorkspace
) -> ResearchAutomationPolicy | None:
    return await session.scalar(
        select(ResearchAutomationPolicy).where(
            ResearchAutomationPolicy.workspace_id == workspace.id,
            ResearchAutomationPolicy.organization_id == workspace.organization_id,
            ResearchAutomationPolicy.tenant_id == workspace.tenant_id,
            ResearchAutomationPolicy.market == workspace.market,
        )
    )


def next_lifecycle_run_at(market: str, *, now: dt.datetime | None = None) -> dt.datetime:
    """Return the next market-session post-close slot in UTC."""

    current = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    timezone = market_timezone(market)
    local_date = current.astimezone(timezone).date()
    delay = _POST_CLOSE_DELAYS[market]
    for offset in range(12):
        candidate = local_date + dt.timedelta(days=offset)
        if not is_trading_day(candidate, market=market):
            continue
        local_close = dt.datetime.combine(
            candidate,
            market_close_on(candidate, market),
            tzinfo=timezone,
        )
        scheduled = (local_close + delay).astimezone(dt.UTC)
        if scheduled > current:
            return scheduled
    raise RuntimeError(f"No verified {market} session was found in the scheduling window")


def expected_lifecycle_session(
    market: str, *, now: dt.datetime | None = None
) -> dt.date | None:
    """Latest session whose configured post-close research slot has elapsed."""

    current = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    timezone = market_timezone(market)
    local_date = current.astimezone(timezone).date()
    delay = _POST_CLOSE_DELAYS[market]
    for offset in range(12):
        candidate = local_date - dt.timedelta(days=offset)
        if not is_trading_day(candidate, market=market):
            continue
        local_close = dt.datetime.combine(
            candidate,
            market_close_on(candidate, market),
            tzinfo=timezone,
        )
        if (local_close + delay).astimezone(dt.UTC) <= current:
            return candidate
    return None


async def upsert_automation_policy(
    session: AsyncSession,
    *,
    workspace: ResearchWorkspace,
    user_id: int,
    payload: AutomationPolicyUpdate,
) -> ResearchAutomationPolicy:
    strategy = STRATEGIES[payload.strategy_key]
    if strategy.market != workspace.market:
        raise ValueError(
            f"Strategy {payload.strategy_key} is not registered for {workspace.market}"
        )
    policy = await get_automation_policy(session, workspace=workspace)
    values: dict[str, Any] = {
        "requested_by_user_id": user_id,
        "enabled": payload.enabled,
        "queue_limit": payload.queue_limit,
        "research_limit": payload.research_limit,
        "cap_tier": payload.cap_tier,
        "strategy_key": payload.strategy_key,
        "universe_limit": payload.universe_limit,
        "initial_capital": Decimal(str(payload.initial_capital)),
        "next_run_at": next_lifecycle_run_at(workspace.market) if payload.enabled else None,
    }
    if policy is None:
        policy = ResearchAutomationPolicy(
            id=uuid.uuid4(),
            organization_id=workspace.organization_id,
            workspace_id=workspace.id,
            tenant_id=workspace.tenant_id,
            market=workspace.market,
            **values,
        )
        session.add(policy)
    else:
        for key, value in values.items():
            setattr(policy, key, value)
    await session.flush()
    return policy


def _research_fingerprint(candidate: Any) -> str:
    return _stable_hash(
        {
            "methodology": candidate.methodology_version,
            "ticker": candidate.ticker,
            "price": candidate.price,
            "factors": candidate.factors.model_dump(mode="json"),
            "factor_details": candidate.factor_details.model_dump(mode="json"),
            "evidence": candidate.evidence.model_dump(mode="json"),
        }
    )


async def execute_research_lifecycle(
    session: AsyncSession,
    *,
    workspace: ResearchWorkspace,
    policy: ResearchAutomationPolicy,
    trigger_key: str,
) -> ResearchRunOut:
    """Run one bounded lifecycle without crossing the caller's RLS-bound workspace."""

    idempotency_key = f"lifecycle:{trigger_key}"[:96]
    existing = await _existing_run(session, workspace=workspace, idempotency_key=idempotency_key)
    if existing is not None:
        return await load_research_run(session, workspace=workspace, run_id=existing.id)

    started = dt.datetime.now(dt.UTC)
    run = _new_run(
        workspace=workspace,
        user_id=policy.requested_by_user_id,
        run_kind="lifecycle",
        question="Advance the registered research, validation, and shadow-evaluation lifecycle.",
        code=None,
        parameters={
            "policy_id": str(policy.id),
            "lifecycle_version": LIFECYCLE_VERSION,
            "trigger_key": trigger_key,
        },
        idempotency_key=idempotency_key,
        cutoff=started,
        code_version=LIFECYCLE_VERSION,
        model="deterministic-coordinator",
    )
    session.add(run)
    await session.flush()

    queue = await build_research_queue(
        session,
        tenant_id=workspace.tenant_id,
        market=workspace.market,
        workspace_id=workspace.id,
        limit=policy.queue_limit,
        cap_tier=policy.cap_tier,
    )
    run.evidence_snapshot_hash = _stable_hash(
        {
            "cutoff": queue.knowledge_cutoff_at,
            "candidates": [
                {"ticker": item.ticker, "fingerprint": _research_fingerprint(item)}
                for item in queue.candidates
            ],
        }
    )
    selected = queue.candidates[: policy.research_limit]
    _add_step(
        session,
        run=run,
        ordinal=0,
        kind="queue_selection",
        output={
            "knowledge_cutoff_at": queue.knowledge_cutoff_at.isoformat(),
            "universe_count": queue.universe_count,
            "eligible_count": queue.eligible_count,
            "queue_limit": policy.queue_limit,
            "selected": [
                {
                    "ticker": item.ticker,
                    "priority": item.priority,
                    "reason": item.queue_reason,
                }
                for item in selected
            ],
        },
    )

    research_records: list[dict[str, Any]] = []
    for candidate in selected:
        fingerprint = _research_fingerprint(candidate)
        research_key = f"auto-r2:{candidate.ticker}:{fingerprint[:40]}"
        previous = await _existing_run(session, workspace=workspace, idempotency_key=research_key)
        try:
            child = await execute_company_research(
                session,
                workspace=workspace,
                user_id=policy.requested_by_user_id,
                code=candidate.ticker,
                idempotency_key=research_key,
            )
            decision = child.parameters.get("decision", {})
            research_records.append(
                {
                    "ticker": candidate.ticker,
                    "run_id": str(child.id),
                    "status": decision.get("status", child.status),
                    "confidence": decision.get("confidence"),
                    "action": "unchanged" if previous is not None else "researched",
                }
            )
        except (LookupError, ValueError) as exc:
            research_records.append(
                {
                    "ticker": candidate.ticker,
                    "status": "failed",
                    "action": "skipped",
                    "error": str(exc),
                }
            )
    _add_step(
        session,
        run=run,
        ordinal=1,
        kind="evidence_changed_research",
        output={"companies": research_records},
        metrics={
            "researched": sum(item["action"] == "researched" for item in research_records),
            "unchanged": sum(item["action"] == "unchanged" for item in research_records),
            "failed": sum(item["status"] == "failed" for item in research_records),
        },
    )

    latest_market_date = await session.scalar(
        select(func.max(DailyBar.date)).where(DailyBar.market == workspace.market)
    )
    backtest_key = (
        f"auto-bt:{policy.strategy_key}:{latest_market_date or 'none'}:"
        f"{_stable_hash([policy.cap_tier, policy.universe_limit, policy.initial_capital])[:20]}"
    )
    backtest: ResearchRunOut | None = None
    backtest_error: str | None = None
    try:
        backtest = await execute_backtest(
            session,
            workspace=workspace,
            user_id=policy.requested_by_user_id,
            request=BacktestRequest(
                idempotency_key=backtest_key,
                strategy_key=policy.strategy_key,
                cap_tier=policy.cap_tier,
                universe_limit=policy.universe_limit,
                initial_capital=float(policy.initial_capital),
            ),
        )
    except ValueError as exc:
        backtest_error = str(exc)
    summary = backtest.parameters.get("result_summary", {}) if backtest else {}
    _add_step(
        session,
        run=run,
        ordinal=2,
        kind="registered_backtest",
        status="failed" if backtest_error else "succeeded",
        error_code="backtest_unavailable" if backtest_error else None,
        output={
            "run_id": str(backtest.id) if backtest else None,
            "validation_status": summary.get("validation_status"),
            "failed_gates": summary.get("failed_gates", []),
            "error": backtest_error,
        },
    )

    shadow_created = False
    shadow_error: str | None = None
    strategy_portfolios = list(
        await session.scalars(
            select(ResearchShadowPortfolio).where(
                ResearchShadowPortfolio.workspace_id == workspace.id,
                ResearchShadowPortfolio.organization_id == workspace.organization_id,
                ResearchShadowPortfolio.tenant_id == workspace.tenant_id,
                ResearchShadowPortfolio.market == workspace.market,
                ResearchShadowPortfolio.strategy_key == policy.strategy_key,
            )
        )
    )
    managed_portfolio = next(
        (
            item
            for item in strategy_portfolios
            if item.configuration.get("managed_by") == "atlas_lifecycle"
        ),
        None,
    )
    if managed_portfolio is None and backtest is not None:
        try:
            created = await create_shadow_portfolio(
                session,
                workspace=workspace,
                user_id=policy.requested_by_user_id,
                request=CreateShadowPortfolioRequest(
                    source_run_id=backtest.id,
                    name=f"Atlas {policy.strategy_key} forward book",
                ),
            )
            managed_portfolio = await session.get(ResearchShadowPortfolio, created.id)
            if managed_portfolio is not None:
                managed_portfolio.configuration = {
                    **managed_portfolio.configuration,
                    "managed_by": "atlas_lifecycle",
                    "automation_policy_id": str(policy.id),
                }
            shadow_created = True
        except (LookupError, ValueError) as exc:
            shadow_error = str(exc)
    portfolios = await reconcile_shadow_portfolios(session, workspace=workspace)
    calibration = await refresh_outcome_observations(session, workspace=workspace)
    managed = next(
        (
            item
            for item in portfolios
            if item.strategy_key == policy.strategy_key
            and item.configuration.get("managed_by") == "atlas_lifecycle"
        ),
        None,
    )
    _add_step(
        session,
        run=run,
        ordinal=3,
        kind="forward_shadow_reconciliation",
        status="failed" if shadow_error else "succeeded",
        error_code="shadow_unavailable" if shadow_error else None,
        output={
            "created": shadow_created,
            "portfolio_id": str(managed.id) if managed else None,
            "last_evaluated_on": (
                managed.last_evaluated_on.isoformat()
                if managed and managed.last_evaluated_on
                else None
            ),
            "promotion": managed.configuration.get("promotion") if managed else None,
            "error": shadow_error,
        },
    )
    _add_step(
        session,
        run=run,
        ordinal=4,
        kind="outcome_calibration",
        output={
            "pending": calibration.pending,
            "matured": calibration.matured,
            "bucket_count": len(calibration.buckets),
        },
    )
    decision_counts: dict[str, int] = {}
    for item in research_records:
        status = str(item["status"])
        decision_counts[status] = decision_counts.get(status, 0) + 1
    run.parameters = {
        **run.parameters,
        "summary": {
            "queue_selected": len(selected),
            "research_decisions": decision_counts,
            "backtest_validation_status": summary.get("validation_status"),
            "shadow_portfolio_id": str(managed.id) if managed else None,
            "promotion_status": (
                managed.configuration.get("promotion", {}).get("status") if managed else None
            ),
            "calibration_pending": calibration.pending,
            "calibration_matured": calibration.matured,
        },
    }
    run.status = "succeeded"
    run.completed_at = dt.datetime.now(dt.UTC)
    await session.flush()
    return await load_research_run(session, workspace=workspace, run_id=run.id)
