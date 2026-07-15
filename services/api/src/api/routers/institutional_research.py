from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Request

from api.deps import CurrentTenant, CurrentUser, DbSession
from api.institutional_research.audit import record_research_audit_event
from api.institutional_research.dossier import (
    ResearchSecurityNotFound,
    build_company_dossier,
)
from api.institutional_research.queue import build_research_queue
from api.institutional_research.schemas import (
    CompanyDossierOut,
    ResearchQueueSnapshotOut,
    WorkspaceOut,
)
from api.institutional_research.workspaces import (
    bootstrap_personal_workspace,
    list_accessible_workspaces,
)
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
