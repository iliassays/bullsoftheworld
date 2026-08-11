from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from api.deps import CurrentTenant, CurrentUser, DbSession
from api.institutional_research.audit import record_research_audit_event
from api.institutional_research.catalysts import load_catalyst_calendar
from api.institutional_research.conditions import (
    load_condition_scan,
    set_condition_subscription,
)
from api.institutional_research.decision_board import (
    load_decision_board,
    load_decision_candidate_path,
)
from api.institutional_research.dossier import (
    ResearchSecurityNotFound,
    build_company_dossier,
)
from api.institutional_research.investment import (
    get_active_mandate,
    load_investment_operating_view,
    mandate_out,
    replace_active_mandate,
)
from api.institutional_research.lifecycle import (
    automation_policy_out,
    get_automation_policy,
    upsert_automation_policy,
)
from api.institutional_research.model_experiments import load_model_experiment_board
from api.institutional_research.options import (
    OptionChainPreviewOut,
    load_option_chain_preview,
)
from api.institutional_research.portfolio import (
    clear_shadow_ladder_freeze,
    create_shadow_portfolio,
    list_shadow_portfolios,
    load_outcome_calibration,
    reconcile_shadow_portfolios,
)
from api.institutional_research.queue import build_research_queue
from api.institutional_research.schemas import (
    AutomationPolicyOut,
    AutomationPolicyUpdate,
    BacktestRequest,
    CalibrationOut,
    CatalystCalendarOut,
    ClearLadderFreezeRequest,
    CompanyDossierOut,
    CreateShadowPortfolioRequest,
    DecisionBoardOut,
    DecisionCandidatePathOut,
    InvestmentMandateOut,
    InvestmentMandateUpdate,
    InvestmentOperatingViewOut,
    LifecycleDispatchOut,
    ModelExperimentBoardOut,
    ResearchConditionScanOut,
    ResearchConditionSubscriptionOut,
    ResearchConditionSubscriptionUpdate,
    ResearchQueueSnapshotOut,
    ResearchRunOut,
    ResearchShadowPortfolioOut,
    SqueezeMonitorOut,
    SqueezePathOut,
    StartResearchRequest,
    StrategyReadinessBoardOut,
    StrategyReadinessOut,
    WorkspaceOut,
)
from api.institutional_research.squeeze import load_squeeze_monitor, load_squeeze_path
from api.institutional_research.universe import apply_research_product_scope
from api.institutional_research.workflow import (
    execute_backtest,
    execute_company_research,
    list_research_runs,
    load_research_run,
)
from api.institutional_research.workspaces import (
    bootstrap_personal_workspace,
    list_accessible_workspaces,
)
from api.queue import enqueue_research_lifecycle
from api.research_access import (
    ResearchAccessDenied,
    ResearchWorkspaceNotFound,
    authorize_research_workspace,
    bind_research_tenant_context,
)
from bulls.analytics.strategy_readiness import readiness_for_market
from bulls.core.models import Symbol
from bulls.core.research_access import ResearchPermission
from bulls.core.symbol_lifecycle import PRIVATE_RESEARCH_STATUSES
from bulls.core.tenancy import Tenant
from bulls.market_data.providers.us_yahoo_options import (
    OptionChainProviderError,
    OptionChainUnavailable,
)

router = APIRouter(prefix="/institutional-research", tags=["institutional-research"])


def _require_research_access(tenant: Tenant) -> None:
    if tenant.research_access != "authenticated":
        raise HTTPException(status_code=403, detail="Research access is not enabled")


def _require_options_preview_access(tenant: Tenant, user) -> None:
    """Fail closed before any provider call; DSE never reveals whether a US chain exists."""

    if tenant.market != "US":
        raise HTTPException(status_code=404, detail="Options are not available for this market")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Owner options preview access required")


async def _authorized_workspace(
    *,
    session,
    workspace_id: uuid.UUID,
    tenant,
    user,
    permission: ResearchPermission,
):
    try:
        return await authorize_research_workspace(
            session,
            workspace_id=workspace_id,
            user_id=user.id,
            tenant_id=tenant.name,
            market=tenant.market,
            permission=permission,
        )
    except ResearchWorkspaceNotFound:
        raise HTTPException(status_code=404, detail="Research workspace not found") from None
    except ResearchAccessDenied as exc:
        raise HTTPException(status_code=403, detail=exc.reason) from None


@router.get("/workspaces")
async def workspaces(
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> list[WorkspaceOut]:
    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    return await list_accessible_workspaces(session, tenant=tenant, user_id=user.id)


@router.post("/workspaces/bootstrap", status_code=201)
async def bootstrap_workspace(
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> WorkspaceOut:
    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    return await bootstrap_personal_workspace(session, tenant=tenant, user=user)


@router.get("/workspaces/{workspace_id}/automation")
async def automation_policy(
    workspace_id: uuid.UUID,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> AutomationPolicyOut | None:
    """Return the workspace policy without creating state on a read."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    authorized = await _authorized_workspace(
        session=session,
        workspace_id=workspace_id,
        tenant=tenant,
        user=user,
        permission=ResearchPermission.VIEW_WORKSPACE,
    )
    policy = await get_automation_policy(session, workspace=authorized.workspace)
    return automation_policy_out(policy) if policy is not None else None


@router.put("/workspaces/{workspace_id}/automation")
async def configure_automation(
    workspace_id: uuid.UUID,
    payload: AutomationPolicyUpdate,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> AutomationPolicyOut:
    """Persist a bounded policy and start its exact-identity job chain when enabled."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    authorized = await _authorized_workspace(
        session=session,
        workspace_id=workspace_id,
        tenant=tenant,
        user=user,
        permission=ResearchPermission.MANAGE_RISK,
    )
    try:
        policy = await upsert_automation_policy(
            session,
            workspace=authorized.workspace,
            user_id=user.id,
            payload=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    record_research_audit_event(
        session,
        workspace=authorized.workspace,
        actor_user_id=user.id,
        event_type="research_automation_configured",
        resource_type="research_automation_policy",
        resource_id=str(policy.id),
        request_id=getattr(request.state, "request_id", None),
        attributes={
            "enabled": policy.enabled,
            "strategy_key": policy.strategy_key,
            "cap_tier": policy.cap_tier,
            "research_limit": policy.research_limit,
        },
    )
    if not policy.enabled:
        await session.flush()
        return automation_policy_out(policy)

    trigger_key = f"enabled:{uuid.uuid4()}"
    job_id = f"atlas:lifecycle:{policy.id}:enable:{uuid.uuid4().hex}"
    policy.last_run_status = "queued"
    policy.last_error = None
    await session.commit()
    try:
        await enqueue_research_lifecycle(
            policy_id=str(policy.id),
            workspace_id=str(policy.workspace_id),
            tenant_id=policy.tenant_id,
            market=policy.market,
            user_id=policy.requested_by_user_id,
            trigger_key=trigger_key,
            job_id=job_id,
            scheduled=False,
        )
    except Exception as exc:
        await bind_research_tenant_context(
            session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
        )
        policy.last_run_status = "failed"
        policy.last_error = f"Lifecycle enqueue failed: {exc}"[:2000]
        await session.commit()
        raise HTTPException(
            status_code=503, detail="Research automation queue unavailable"
        ) from None
    return automation_policy_out(policy)


@router.get("/workspaces/{workspace_id}/investment-mandate")
async def investment_mandate(
    workspace_id: uuid.UUID,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> InvestmentMandateOut:
    """Return the active, versioned portfolio authority for this market workspace."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    authorized = await _authorized_workspace(
        session=session,
        workspace_id=workspace_id,
        tenant=tenant,
        user=user,
        permission=ResearchPermission.VIEW_WORKSPACE,
    )
    mandate = await get_active_mandate(session, workspace=authorized.workspace)
    if mandate is None:
        raise HTTPException(status_code=409, detail="Investment mandate is not configured")
    return mandate_out(mandate)


@router.put("/workspaces/{workspace_id}/investment-mandate")
async def configure_investment_mandate(
    workspace_id: uuid.UUID,
    payload: InvestmentMandateUpdate,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> InvestmentMandateOut:
    """Create a new mandate version; existing paper books retain their pinned version."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    authorized = await _authorized_workspace(
        session=session,
        workspace_id=workspace_id,
        tenant=tenant,
        user=user,
        permission=ResearchPermission.MANAGE_RISK,
    )
    try:
        mandate = await replace_active_mandate(
            session,
            workspace=authorized.workspace,
            user_id=user.id,
            payload=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    record_research_audit_event(
        session,
        workspace=authorized.workspace,
        actor_user_id=user.id,
        event_type="investment_mandate_replaced",
        resource_type="investment_mandate",
        resource_id=str(mandate.id),
        request_id=getattr(request.state, "request_id", None),
        attributes={
            "version": mandate.version,
            "specification_hash": mandate.specification_hash,
        },
    )
    return mandate


@router.get("/workspaces/{workspace_id}/investment-operating-view")
async def investment_operating_view(
    workspace_id: uuid.UUID,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> InvestmentOperatingViewOut:
    """Compose mandate, trial, risk, attribution, and decision-lineage read models."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    authorized = await _authorized_workspace(
        session=session,
        workspace_id=workspace_id,
        tenant=tenant,
        user=user,
        permission=ResearchPermission.VIEW_WORKSPACE,
    )
    try:
        return await load_investment_operating_view(session, workspace=authorized.workspace)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.get("/strategy-readiness")
async def strategy_readiness(
    tenant: CurrentTenant,
    user: CurrentUser,
) -> StrategyReadinessBoardOut:
    """List every evaluated strategy family for this market, including blocked ones.

    The catalog is declarative code (`bulls.analytics.strategy_readiness`), not a computation:
    blocked strategies are registered with the exact datasets they are missing so the UI shows
    the audited reason, never render-time prose.
    """

    _require_research_access(tenant)
    return StrategyReadinessBoardOut(
        market=tenant.market,
        tenant_id=tenant.name,
        generated_at=dt.datetime.now(dt.UTC),
        entries=[
            StrategyReadinessOut.model_validate(entry.model_dump())
            for entry in readiness_for_market(tenant.market)
        ],
        methodology=(
            "Statuses come from the 2026-07-24 data audit: backtest_ready requires "
            "point-in-time inputs for a gated historical run; diagnostic_only means a known "
            "data defect caps every result below promotion; blocked means a required dataset "
            "does not exist. Changing a status is a reviewed code change, not a runtime "
            "decision."
        ),
    )


@router.get("/model-experiments/latest")
async def latest_model_experiment(
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> ModelExperimentBoardOut:
    """Return this market's latest offline model audit and certified universe state."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    return await load_model_experiment_board(
        session,
        tenant_id=tenant.name,
        market=tenant.market,
    )


@router.get("/squeeze-monitor")
async def squeeze_monitor(
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
    as_of: Annotated[dt.date | None, Query()] = None,
) -> SqueezeMonitorOut:
    """Read the archived squeeze-taxonomy states for this tenant's market.

    Blocked families (short squeeze, gamma squeeze, float squeeze) are returned as explicit
    data-blocked entries with their missing datasets — absence is an answer, never a gap.
    """

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    return await load_squeeze_monitor(
        session,
        tenant_id=tenant.name,
        market=tenant.market,
        as_of=as_of,
    )


@router.get("/squeeze-monitor/{family}/{code}")
async def squeeze_path(
    family: str,
    code: str,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
    as_of: Annotated[dt.date | None, Query()] = None,
) -> SqueezePathOut:
    """Read candles, overlays and the archived state progression for one squeeze setup."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    try:
        return await load_squeeze_path(
            session,
            tenant_id=tenant.name,
            market=tenant.market,
            family=family,
            code=code,
            as_of=as_of,
        )
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail="Squeeze setup not found in this archived session",
        ) from None


@router.get("/workspaces/{workspace_id}/decision-board")
async def decision_board(
    workspace_id: uuid.UUID,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
    as_of: Annotated[dt.date | None, Query()] = None,
) -> DecisionBoardOut:
    """Read the current or archived strategy decision snapshot without mutating paper books."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    authorized = await _authorized_workspace(
        session=session,
        workspace_id=workspace_id,
        tenant=tenant,
        user=user,
        permission=ResearchPermission.VIEW_WORKSPACE,
    )
    return await load_decision_board(
        session,
        workspace=authorized.workspace,
        as_of=as_of,
    )


@router.get("/workspaces/{workspace_id}/decision-board/{portfolio_id}/{code}")
async def decision_candidate_path(
    workspace_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    code: str,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
    as_of: Annotated[dt.date | None, Query()] = None,
) -> DecisionCandidatePathOut:
    """Read one candidate's discovery-to-snapshot price path and causal strategy events."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    authorized = await _authorized_workspace(
        session=session,
        workspace_id=workspace_id,
        tenant=tenant,
        user=user,
        permission=ResearchPermission.VIEW_WORKSPACE,
    )
    try:
        return await load_decision_candidate_path(
            session,
            workspace=authorized.workspace,
            portfolio_id=portfolio_id,
            code=code,
            as_of=as_of,
        )
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail="Decision candidate not found in this workspace snapshot",
        ) from None


@router.post("/workspaces/{workspace_id}/automation/run", status_code=202)
async def run_automation_now(
    workspace_id: uuid.UUID,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> LifecycleDispatchOut:
    """Dispatch one manual lifecycle run; it does not change the recurring enabled state."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    authorized = await _authorized_workspace(
        session=session,
        workspace_id=workspace_id,
        tenant=tenant,
        user=user,
        permission=ResearchPermission.MANAGE_RISK,
    )
    policy = await get_automation_policy(session, workspace=authorized.workspace)
    if policy is None:
        raise HTTPException(status_code=409, detail="Configure the lifecycle policy first")
    now = dt.datetime.now(dt.UTC)
    trigger_key = f"manual:{uuid.uuid4()}"
    job_id = f"atlas:lifecycle:{policy.id}:manual:{uuid.uuid4().hex}"
    policy.last_run_status = "queued"
    policy.last_error = None
    record_research_audit_event(
        session,
        workspace=authorized.workspace,
        actor_user_id=user.id,
        event_type="research_lifecycle_dispatched",
        resource_type="research_automation_policy",
        resource_id=str(policy.id),
        request_id=getattr(request.state, "request_id", None),
        attributes={"job_id": job_id, "trigger": "manual"},
    )
    await session.commit()
    try:
        accepted = await enqueue_research_lifecycle(
            policy_id=str(policy.id),
            workspace_id=str(policy.workspace_id),
            tenant_id=policy.tenant_id,
            market=policy.market,
            user_id=policy.requested_by_user_id,
            trigger_key=trigger_key,
            job_id=job_id,
            scheduled=False,
        )
    except Exception as exc:
        await bind_research_tenant_context(
            session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
        )
        policy.last_run_status = "failed"
        policy.last_error = f"Lifecycle enqueue failed: {exc}"[:2000]
        await session.commit()
        raise HTTPException(
            status_code=503, detail="Research automation queue unavailable"
        ) from None
    return LifecycleDispatchOut(accepted=accepted, job_id=job_id, scheduled_for=now)


@router.get("/workspaces/{workspace_id}/queue")
async def research_queue(
    workspace_id: uuid.UUID,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
    limit: int = Query(100, ge=1, le=250),
    cap_tier: str | None = Query(
        None,
        pattern="^(mega|large|mid|small|micro|penny|unclassified)$",
    ),
    query: str | None = Query(None, min_length=1, max_length=64),
) -> ResearchQueueSnapshotOut:
    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    try:
        await authorize_research_workspace(
            session,
            workspace_id=workspace_id,
            user_id=user.id,
            tenant_id=tenant.name,
            market=tenant.market,
            permission=ResearchPermission.VIEW_WORKSPACE,
        )
    except ResearchWorkspaceNotFound:
        raise HTTPException(status_code=404, detail="Research workspace not found") from None
    except ResearchAccessDenied as exc:
        raise HTTPException(status_code=403, detail=exc.reason) from None

    return await build_research_queue(
        session,
        tenant_id=tenant.name,
        market=tenant.market,
        workspace_id=workspace_id,
        limit=limit,
        cap_tier=cap_tier,
        query=query,
    )


@router.get("/workspaces/{workspace_id}/condition-scan")
async def condition_scan(
    workspace_id: uuid.UUID,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
    condition_key: str = Query(
        "trend_alignment",
        pattern="^(trend_alignment|participation_expansion|controlled_pullback_context)$",
    ),
    cap_tier: str | None = Query(
        None,
        pattern="^(mega|large|mid|small|micro|penny|unclassified)$",
    ),
    new_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=250),
) -> ResearchConditionScanOut:
    """Return calibrated completed-session condition evidence, never a trade queue."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    await _authorized_workspace(
        session=session,
        workspace_id=workspace_id,
        tenant=tenant,
        user=user,
        permission=ResearchPermission.VIEW_WORKSPACE,
    )
    return await load_condition_scan(
        session,
        tenant_id=tenant.name,
        market=tenant.market,
        workspace_id=workspace_id,
        user_id=user.id,
        condition_key=condition_key,
        cap_tier=cap_tier,
        new_only=new_only,
        limit=limit,
    )


@router.put("/workspaces/{workspace_id}/condition-subscriptions/{condition_key}/{code}")
async def configure_condition_subscription(
    workspace_id: uuid.UUID,
    condition_key: str,
    code: str,
    payload: ResearchConditionSubscriptionUpdate,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> ResearchConditionSubscriptionOut:
    """Opt in to a future observation alert for one exact ticker and condition."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    authorized = await _authorized_workspace(
        session=session,
        workspace_id=workspace_id,
        tenant=tenant,
        user=user,
        permission=ResearchPermission.VIEW_WORKSPACE,
    )
    try:
        subscription = await set_condition_subscription(
            session,
            tenant_id=tenant.name,
            market=tenant.market,
            user_id=user.id,
            code=code,
            condition_key=condition_key,
            enabled=payload.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    record_research_audit_event(
        session,
        workspace=authorized.workspace,
        actor_user_id=user.id,
        event_type="research_condition_subscription_changed",
        resource_type="security_condition",
        resource_id=f"{tenant.market}:{subscription.ticker}:{condition_key}",
        request_id=getattr(request.state, "request_id", None),
        attributes={"enabled": payload.enabled},
    )
    return subscription


@router.get("/workspaces/{workspace_id}/catalysts")
async def catalyst_calendar(
    workspace_id: uuid.UUID,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
    horizon_days: int = Query(60, ge=7, le=180),
    code: str | None = Query(None, min_length=1, max_length=16),
) -> CatalystCalendarOut:
    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    try:
        await authorize_research_workspace(
            session,
            workspace_id=workspace_id,
            user_id=user.id,
            tenant_id=tenant.name,
            market=tenant.market,
            permission=ResearchPermission.VIEW_WORKSPACE,
        )
    except ResearchWorkspaceNotFound:
        raise HTTPException(status_code=404, detail="Research workspace not found") from None
    except ResearchAccessDenied as exc:
        raise HTTPException(status_code=403, detail=exc.reason) from None

    return await load_catalyst_calendar(
        session,
        tenant_id=tenant.name,
        market=tenant.market,
        workspace_id=workspace_id,
        horizon_days=horizon_days,
        code=code,
    )


@router.get("/workspaces/{workspace_id}/companies/{code}")
async def company_dossier(
    workspace_id: uuid.UUID,
    code: str,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> CompanyDossierOut:
    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    try:
        authorized = await authorize_research_workspace(
            session,
            workspace_id=workspace_id,
            user_id=user.id,
            tenant_id=tenant.name,
            market=tenant.market,
            permission=ResearchPermission.VIEW_WORKSPACE,
        )
    except ResearchWorkspaceNotFound:
        raise HTTPException(status_code=404, detail="Research workspace not found") from None
    except ResearchAccessDenied as exc:
        raise HTTPException(status_code=403, detail=exc.reason) from None

    try:
        dossier = await build_company_dossier(
            session,
            tenant_id=tenant.name,
            market=tenant.market,
            workspace_id=workspace_id,
            code=code,
        )
    except ResearchSecurityNotFound:
        raise HTTPException(
            status_code=404,
            detail="Security is not available in this research tenant",
        ) from None
    record_research_audit_event(
        session,
        workspace=authorized.workspace,
        actor_user_id=user.id,
        event_type="company_dossier_viewed",
        resource_type="security",
        resource_id=f"{tenant.market}:{dossier.candidate.ticker}",
        request_id=getattr(request.state, "request_id", None),
        attributes={"knowledge_cutoff_at": dossier.knowledge_cutoff_at.isoformat()},
    )
    return dossier


@router.get("/workspaces/{workspace_id}/companies/{code}/options-chain")
async def company_option_chain(
    workspace_id: uuid.UUID,
    code: str,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
    expiration: Annotated[dt.date | None, Query()] = None,
) -> OptionChainPreviewOut:
    """Load one delayed US chain without coupling it to the core company dossier."""

    _require_research_access(tenant)
    _require_options_preview_access(tenant, user)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    authorized = await _authorized_workspace(
        session=session,
        workspace_id=workspace_id,
        tenant=tenant,
        user=user,
        permission=ResearchPermission.VIEW_WORKSPACE,
    )
    normalized = code.strip().upper()
    symbol_statement = select(Symbol.code).where(
        Symbol.market == "US",
        Symbol.code == normalized,
        Symbol.is_active.is_(True),
        Symbol.is_hidden.is_(False),
        Symbol.research_status.in_(PRIVATE_RESEARCH_STATUSES),
    )
    symbol = await session.scalar(apply_research_product_scope(symbol_statement, market="US"))
    if symbol is None:
        raise HTTPException(
            status_code=404,
            detail="Security is not available in this research tenant",
        )

    try:
        preview = await load_option_chain_preview(
            tenant_id=tenant.name,
            workspace_id=workspace_id,
            code=normalized,
            expiration=expiration,
        )
    except OptionChainUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except OptionChainProviderError:
        raise HTTPException(
            status_code=503,
            detail="The experimental option-chain source is temporarily unavailable",
        ) from None

    record_research_audit_event(
        session,
        workspace=authorized.workspace,
        actor_user_id=user.id,
        event_type="option_chain_preview_viewed",
        resource_type="security",
        resource_id=f"US:{normalized}",
        request_id=getattr(request.state, "request_id", None),
        attributes={
            "expiration": preview.expiration.isoformat(),
            "provider": preview.provider,
            "quality": preview.metrics.quality,
        },
    )
    return preview


@router.post(
    "/workspaces/{workspace_id}/companies/{code}/research-runs",
    status_code=201,
)
async def start_company_research(
    workspace_id: uuid.UUID,
    code: str,
    payload: StartResearchRequest,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> ResearchRunOut:
    """Run the autonomous analyst, skeptic, verifier, and evidence/risk decision gate."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    try:
        authorized = await authorize_research_workspace(
            session,
            workspace_id=workspace_id,
            user_id=user.id,
            tenant_id=tenant.name,
            market=tenant.market,
            permission=ResearchPermission.RUN_RESEARCH,
        )
        run = await execute_company_research(
            session,
            workspace=authorized.workspace,
            user_id=user.id,
            code=code,
            idempotency_key=payload.idempotency_key,
        )
    except ResearchWorkspaceNotFound:
        raise HTTPException(status_code=404, detail="Research workspace not found") from None
    except ResearchAccessDenied as exc:
        raise HTTPException(status_code=403, detail=exc.reason) from None
    except ResearchSecurityNotFound:
        raise HTTPException(
            status_code=404, detail="Security is not available in this research tenant"
        ) from None
    record_research_audit_event(
        session,
        workspace=authorized.workspace,
        actor_user_id=user.id,
        event_type="autonomous_research_completed",
        resource_type="research_run",
        resource_id=str(run.id),
        request_id=getattr(request.state, "request_id", None),
        attributes={"code": run.code, "status": run.parameters.get("decision", {}).get("status")},
    )
    return run


@router.post("/workspaces/{workspace_id}/backtests", status_code=201)
async def start_backtest(
    workspace_id: uuid.UUID,
    payload: BacktestRequest,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> ResearchRunOut:
    """Run a registered point-in-time strategy through the deterministic portfolio/risk engine."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    try:
        authorized = await authorize_research_workspace(
            session,
            workspace_id=workspace_id,
            user_id=user.id,
            tenant_id=tenant.name,
            market=tenant.market,
            permission=ResearchPermission.MANAGE_HYPOTHESES,
        )
        run = await execute_backtest(
            session,
            workspace=authorized.workspace,
            user_id=user.id,
            request=payload,
        )
    except ResearchWorkspaceNotFound:
        raise HTTPException(status_code=404, detail="Research workspace not found") from None
    except ResearchAccessDenied as exc:
        raise HTTPException(status_code=403, detail=exc.reason) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    record_research_audit_event(
        session,
        workspace=authorized.workspace,
        actor_user_id=user.id,
        event_type="research_backtest_completed",
        resource_type="research_run",
        resource_id=str(run.id),
        request_id=getattr(request.state, "request_id", None),
        attributes={
            "strategy_key": payload.strategy_key,
            "validation_status": run.parameters.get("result_summary", {}).get("validation_status"),
        },
    )
    return run


@router.get("/workspaces/{workspace_id}/runs")
async def research_runs(
    workspace_id: uuid.UUID,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
    limit: int = Query(50, ge=1, le=100),
) -> list[ResearchRunOut]:
    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    try:
        authorized = await authorize_research_workspace(
            session,
            workspace_id=workspace_id,
            user_id=user.id,
            tenant_id=tenant.name,
            market=tenant.market,
            permission=ResearchPermission.VIEW_WORKSPACE,
        )
    except ResearchWorkspaceNotFound:
        raise HTTPException(status_code=404, detail="Research workspace not found") from None
    except ResearchAccessDenied as exc:
        raise HTTPException(status_code=403, detail=exc.reason) from None
    return await list_research_runs(session, workspace=authorized.workspace, limit=limit)


@router.get("/workspaces/{workspace_id}/runs/{run_id}")
async def research_run(
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> ResearchRunOut:
    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    try:
        authorized = await authorize_research_workspace(
            session,
            workspace_id=workspace_id,
            user_id=user.id,
            tenant_id=tenant.name,
            market=tenant.market,
            permission=ResearchPermission.VIEW_WORKSPACE,
        )
        return await load_research_run(session, workspace=authorized.workspace, run_id=run_id)
    except (ResearchWorkspaceNotFound, LookupError):
        raise HTTPException(status_code=404, detail="Research run not found") from None
    except ResearchAccessDenied as exc:
        raise HTTPException(status_code=403, detail=exc.reason) from None


@router.post("/workspaces/{workspace_id}/shadow-portfolios", status_code=201)
async def start_shadow_portfolio(
    workspace_id: uuid.UUID,
    payload: CreateShadowPortfolioRequest,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> ResearchShadowPortfolioOut:
    """Start a no-broker shadow book from a completed backtest run."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    try:
        authorized = await authorize_research_workspace(
            session,
            workspace_id=workspace_id,
            user_id=user.id,
            tenant_id=tenant.name,
            market=tenant.market,
            permission=ResearchPermission.MANAGE_RISK,
        )
        portfolio = await create_shadow_portfolio(
            session,
            workspace=authorized.workspace,
            user_id=user.id,
            request=payload,
        )
    except ResearchWorkspaceNotFound:
        raise HTTPException(status_code=404, detail="Research workspace not found") from None
    except ResearchAccessDenied as exc:
        raise HTTPException(status_code=403, detail=exc.reason) from None
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="A shadow portfolio with this name already exists in the workspace",
        ) from None
    record_research_audit_event(
        session,
        workspace=authorized.workspace,
        actor_user_id=user.id,
        event_type="shadow_portfolio_started",
        resource_type="research_shadow_portfolio",
        resource_id=str(portfolio.id),
        request_id=getattr(request.state, "request_id", None),
        attributes={
            "source_run_id": str(payload.source_run_id),
            "strategy_key": portfolio.strategy_key,
        },
    )
    return portfolio


@router.get("/workspaces/{workspace_id}/shadow-portfolios")
async def shadow_portfolios(
    workspace_id: uuid.UUID,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> list[ResearchShadowPortfolioOut]:
    """Read shadow books without mutating their execution ledger."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    try:
        authorized = await authorize_research_workspace(
            session,
            workspace_id=workspace_id,
            user_id=user.id,
            tenant_id=tenant.name,
            market=tenant.market,
            permission=ResearchPermission.VIEW_WORKSPACE,
        )
    except ResearchWorkspaceNotFound:
        raise HTTPException(status_code=404, detail="Research workspace not found") from None
    except ResearchAccessDenied as exc:
        raise HTTPException(status_code=403, detail=exc.reason) from None
    return await list_shadow_portfolios(session, workspace=authorized.workspace)


@router.post("/workspaces/{workspace_id}/shadow-portfolios/reconcile")
async def reconcile_workspace_shadow_portfolios(
    workspace_id: uuid.UUID,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> list[ResearchShadowPortfolioOut]:
    """Catch shadow books up without making a read request mutate investment records."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    try:
        authorized = await authorize_research_workspace(
            session,
            workspace_id=workspace_id,
            user_id=user.id,
            tenant_id=tenant.name,
            market=tenant.market,
            permission=ResearchPermission.MANAGE_RISK,
        )
        portfolios = await reconcile_shadow_portfolios(session, workspace=authorized.workspace)
    except ResearchWorkspaceNotFound:
        raise HTTPException(status_code=404, detail="Research workspace not found") from None
    except ResearchAccessDenied as exc:
        raise HTTPException(status_code=403, detail=exc.reason) from None
    record_research_audit_event(
        session,
        workspace=authorized.workspace,
        actor_user_id=user.id,
        event_type="shadow_portfolios_reconciled",
        resource_type="research_workspace",
        resource_id=str(workspace_id),
        request_id=getattr(request.state, "request_id", None),
        attributes={"portfolio_count": len(portfolios)},
    )
    return portfolios


@router.post("/workspaces/{workspace_id}/shadow-portfolios/{portfolio_id}/clear-ladder-freeze")
async def clear_shadow_portfolio_ladder_freeze(
    workspace_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    payload: ClearLadderFreezeRequest,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> ResearchShadowPortfolioOut:
    """Re-arm a book the drawdown ladder froze, recording the written review as an override."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    try:
        authorized = await authorize_research_workspace(
            session,
            workspace_id=workspace_id,
            user_id=user.id,
            tenant_id=tenant.name,
            market=tenant.market,
            permission=ResearchPermission.MANAGE_RISK,
        )
        portfolio = await clear_shadow_ladder_freeze(
            session,
            workspace=authorized.workspace,
            portfolio_id=portfolio_id,
            user_id=user.id,
            reason=payload.reason,
        )
    except ResearchWorkspaceNotFound:
        raise HTTPException(status_code=404, detail="Research workspace not found") from None
    except ResearchAccessDenied as exc:
        raise HTTPException(status_code=403, detail=exc.reason) from None
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    record_research_audit_event(
        session,
        workspace=authorized.workspace,
        actor_user_id=user.id,
        event_type="shadow_portfolio_ladder_freeze_cleared",
        resource_type="research_shadow_portfolio",
        resource_id=str(portfolio_id),
        request_id=getattr(request.state, "request_id", None),
        attributes={"reason_length": len(payload.reason)},
    )
    return portfolio


@router.get("/workspaces/{workspace_id}/calibration")
async def research_calibration(
    workspace_id: uuid.UUID,
    tenant: CurrentTenant,
    user: CurrentUser,
    session: DbSession,
) -> CalibrationOut:
    """Measure forward outcomes without allowing outcomes to rewrite historical decisions."""

    _require_research_access(tenant)
    await bind_research_tenant_context(
        session, tenant_id=tenant.name, market=tenant.market, user_id=user.id
    )
    try:
        authorized = await authorize_research_workspace(
            session,
            workspace_id=workspace_id,
            user_id=user.id,
            tenant_id=tenant.name,
            market=tenant.market,
            permission=ResearchPermission.VIEW_WORKSPACE,
        )
    except ResearchWorkspaceNotFound:
        raise HTTPException(status_code=404, detail="Research workspace not found") from None
    except ResearchAccessDenied as exc:
        raise HTTPException(status_code=403, detail=exc.reason) from None
    return await load_outcome_calibration(session, workspace=authorized.workspace)
