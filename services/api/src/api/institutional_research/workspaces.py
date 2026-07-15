from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from api.institutional_research.audit import record_research_audit_event
from api.institutional_research.schemas import WorkspaceOut
from bulls.core.markets import get_market_profile
from bulls.core.models import (
    ResearchOrganization,
    ResearchOrganizationMembership,
    ResearchWorkspace,
    ResearchWorkspaceMembership,
    User,
)
from bulls.core.tenancy import Tenant


async def list_accessible_workspaces(
    session: AsyncSession,
    *,
    tenant: Tenant,
    user_id: int,
) -> list[WorkspaceOut]:
    organization_membership = aliased(ResearchOrganizationMembership)
    workspace_membership = aliased(ResearchWorkspaceMembership)
    rows = (
        await session.execute(
            select(
                ResearchWorkspace,
                ResearchOrganization.name.label("organization_name"),
                organization_membership.role.label("organization_role"),
                workspace_membership.role.label("workspace_role"),
            )
            .join(
                ResearchOrganization,
                and_(
                    ResearchOrganization.id == ResearchWorkspace.organization_id,
                    ResearchOrganization.tenant_id == tenant.name,
                    ResearchOrganization.market == tenant.market,
                ),
            )
            .join(
                organization_membership,
                and_(
                    organization_membership.organization_id == ResearchWorkspace.organization_id,
                    organization_membership.tenant_id == tenant.name,
                    organization_membership.market == tenant.market,
                    organization_membership.user_id == user_id,
                    organization_membership.status == "active",
                ),
            )
            .outerjoin(
                workspace_membership,
                and_(
                    workspace_membership.workspace_id == ResearchWorkspace.id,
                    workspace_membership.organization_id == ResearchWorkspace.organization_id,
                    workspace_membership.tenant_id == tenant.name,
                    workspace_membership.market == tenant.market,
                    workspace_membership.user_id == user_id,
                    workspace_membership.status == "active",
                ),
            )
            .where(
                ResearchWorkspace.tenant_id == tenant.name,
                ResearchWorkspace.market == tenant.market,
                ResearchWorkspace.status == "active",
                ResearchOrganization.status == "active",
                or_(
                    organization_membership.role.in_(("owner", "admin")),
                    workspace_membership.user_id.is_not(None),
                ),
            )
            .order_by(ResearchWorkspace.name, ResearchWorkspace.id)
        )
    ).all()
    return [
        WorkspaceOut(
            id=workspace.id,
            organization_id=workspace.organization_id,
            organization_name=organization_name,
            tenant_id=workspace.tenant_id,
            market=workspace.market,
            name=workspace.name,
            base_currency=workspace.base_currency,
            organization_role=organization_role,
            workspace_role=workspace_role,
        )
        for workspace, organization_name, organization_role, workspace_role in rows
    ]


async def bootstrap_personal_workspace(
    session: AsyncSession,
    *,
    tenant: Tenant,
    user: User,
) -> WorkspaceOut:
    """Create an idempotent tenant-bound private workspace for an authenticated analyst."""

    # Serialize bootstrap for one tenant/user. Without this transaction lock, two initial page
    # loads could both observe no workspace and race into a uniqueness error.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
        {"identity": f"research-bootstrap:{tenant.name}:{tenant.market}:{user.id}"},
    )

    existing = await list_accessible_workspaces(session, tenant=tenant, user_id=user.id)
    if existing:
        return existing[0]

    organization = await session.scalar(
        select(ResearchOrganization).where(
            ResearchOrganization.tenant_id == tenant.name,
            ResearchOrganization.market == tenant.market,
            ResearchOrganization.slug == f"personal-{user.id}",
        )
    )
    if organization is None:
        organization = ResearchOrganization(
            id=uuid.uuid4(),
            tenant_id=tenant.name,
            market=tenant.market,
            slug=f"personal-{user.id}",
            name=f"{user.name} Research",
            created_by_user_id=user.id,
        )
        session.add(organization)
        await session.flush()

    organization_membership = await session.get(
        ResearchOrganizationMembership,
        (organization.id, user.id),
    )
    if organization_membership is None:
        organization_membership = ResearchOrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            tenant_id=tenant.name,
            market=tenant.market,
            role="owner",
            status="active",
            invited_by_user_id=user.id,
            activated_at=dt.datetime.now(dt.UTC),
        )
        session.add(organization_membership)
        await session.flush()

    workspace = await session.scalar(
        select(ResearchWorkspace).where(
            ResearchWorkspace.organization_id == organization.id,
            ResearchWorkspace.tenant_id == tenant.name,
            ResearchWorkspace.market == tenant.market,
            ResearchWorkspace.slug == "core-equity",
        )
    )
    if workspace is None:
        workspace = ResearchWorkspace(
            id=uuid.uuid4(),
            organization_id=organization.id,
            tenant_id=tenant.name,
            market=tenant.market,
            slug="core-equity",
            name="Core equity",
            base_currency=get_market_profile(tenant.market).currency_code,
            created_by_user_id=user.id,
        )
        session.add(workspace)
        await session.flush()

    membership = await session.get(ResearchWorkspaceMembership, (workspace.id, user.id))
    if membership is None:
        session.add(
            ResearchWorkspaceMembership(
                workspace_id=workspace.id,
                user_id=user.id,
                organization_id=organization.id,
                tenant_id=tenant.name,
                market=tenant.market,
                role="portfolio_manager",
                status="active",
                granted_by_user_id=user.id,
            )
        )
        await session.flush()

    record_research_audit_event(
        session,
        workspace=workspace,
        actor_user_id=user.id,
        event_type="workspace_bootstrapped",
        resource_type="workspace",
        resource_id=str(workspace.id),
        attributes={"organization_id": str(organization.id)},
    )

    return WorkspaceOut(
        id=workspace.id,
        organization_id=organization.id,
        organization_name=organization.name,
        tenant_id=tenant.name,
        market=tenant.market,
        name=workspace.name,
        base_currency=workspace.base_currency,
        organization_role="owner",
        workspace_role="portfolio_manager",
    )
