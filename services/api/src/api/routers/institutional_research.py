from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError

from api.deps import CurrentTenant, CurrentUser, DbSession
from api.institutional_research.audit import record_research_audit_event
from api.institutional_research.catalysts import load_catalyst_calendar
from api.institutional_research.dossier import (
    ResearchSecurityNotFound,
    build_company_dossier,
)
from api.institutional_research.lifecycle import (
    automation_policy_out,
    get_automation_policy,
    upsert_automation_policy,
)
from api.institutional_research.portfolio import (
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
    CompanyDossierOut,
    CreateShadowPortfolioRequest,
    LifecycleDispatchOut,
    ResearchQueueSnapshotOut,
    ResearchRunOut,
    ResearchShadowPortfolioOut,
    StartResearchRequest,
    WorkspaceOut,
)
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
from bulls.core.research_access import ResearchPermission
from bulls.core.tenancy import Tenant

router = APIRouter(prefix="/institutional-research", tags=["institutional-research"])


def _require_research_access(tenant: Tenant) -> None:
    if tenant.research_access != "authenticated":
        raise HTTPException(status_code=403, detail="Research access is not enabled")


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
