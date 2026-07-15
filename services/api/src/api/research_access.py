"""Database-backed access boundary for all institutional research APIs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import Select, and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from bulls.core.db import bind_tenant_context
from bulls.core.models import (
    ResearchOrganization,
    ResearchOrganizationMembership,
    ResearchWorkspace,
    ResearchWorkspaceMembership,
)
from bulls.core.research_access import (
    ResearchAccessContext,
    ResearchPermission,
    evaluate_research_access,
)


class ResearchWorkspaceNotFound(LookupError):
    """The workspace does not exist, or should not be disclosed to this caller."""


class ResearchAccessDenied(PermissionError):
    """An authenticated user lacks the requested workspace permission."""

    def __init__(self, reason: str) -> None:
        super().__init__("Research workspace access denied")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class AuthorizedResearchWorkspace:
    workspace: ResearchWorkspace
    organization_role: str
    workspace_role: str | None


async def bind_research_tenant_context(
    session: AsyncSession,
    *,
    tenant_id: str,
    market: str,
    user_id: int,
) -> None:
    """Set transaction-local values consumed by research-table row security policies."""

    await bind_tenant_context(session, tenant_id)
    await session.execute(
        text(
            "SELECT "
            "set_config('app.research_tenant_id', :tenant_id, true), "
            "set_config('app.research_market', :market, true), "
            "set_config('app.research_user_id', :user_id, true)"
        ),
        {"tenant_id": tenant_id, "market": market, "user_id": str(user_id)},
    )


def workspace_access_statement(
    workspace_id: uuid.UUID,
    user_id: int,
    *,
    tenant_id: str,
    market: str,
) -> Select:
    """Build the IDOR-resistant lookup used by every workspace-scoped endpoint."""

    organization_membership = aliased(ResearchOrganizationMembership)
    workspace_membership = aliased(ResearchWorkspaceMembership)
    return (
        select(
            ResearchWorkspace,
            ResearchOrganization.status.label("organization_status"),
            organization_membership.status.label("organization_membership_status"),
            organization_membership.role.label("organization_role"),
            workspace_membership.status.label("workspace_membership_status"),
            workspace_membership.role.label("workspace_role"),
        )
        .join(
            ResearchOrganization,
            ResearchOrganization.id == ResearchWorkspace.organization_id,
        )
        .outerjoin(
            organization_membership,
            and_(
                organization_membership.organization_id == ResearchWorkspace.organization_id,
                organization_membership.user_id == user_id,
                organization_membership.tenant_id == tenant_id,
                organization_membership.market == market,
            ),
        )
        .outerjoin(
            workspace_membership,
            and_(
                workspace_membership.workspace_id == ResearchWorkspace.id,
                workspace_membership.organization_id == ResearchWorkspace.organization_id,
                workspace_membership.user_id == user_id,
                workspace_membership.tenant_id == tenant_id,
                workspace_membership.market == market,
            ),
        )
        .where(
            ResearchWorkspace.id == workspace_id,
            ResearchWorkspace.tenant_id == tenant_id,
            ResearchWorkspace.market == market,
            ResearchOrganization.tenant_id == tenant_id,
            ResearchOrganization.market == market,
        )
    )


async def authorize_research_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: int,
    tenant_id: str,
    market: str,
    permission: ResearchPermission,
) -> AuthorizedResearchWorkspace:
    """Load a workspace and enforce its organization/workspace policy in one query."""

    row = (
        await session.execute(
            workspace_access_statement(
                workspace_id,
                user_id,
                tenant_id=tenant_id,
                market=market,
            )
        )
    ).one_or_none()
    if row is None:
        raise ResearchWorkspaceNotFound

    # Do not reveal that a private workspace exists to users outside its organization or outside
    # that workspace. Organization owners/admins are explicit administrators of all workspaces.
    if row.organization_membership_status is None:
        raise ResearchWorkspaceNotFound
    if row.organization_role == "member" and row.workspace_membership_status is None:
        raise ResearchWorkspaceNotFound

    workspace = row[0]
    if workspace.tenant_id != tenant_id or workspace.market != market:
        raise ResearchWorkspaceNotFound
    decision = evaluate_research_access(
        ResearchAccessContext(
            organization_status=row.organization_status,
            organization_membership_status=row.organization_membership_status,
            organization_role=row.organization_role,
            workspace_status=workspace.status,
            workspace_membership_status=row.workspace_membership_status,
            workspace_role=row.workspace_role,
        ),
        permission,
    )
    if not decision.allowed:
        raise ResearchAccessDenied(decision.reason)

    return AuthorizedResearchWorkspace(
        workspace=workspace,
        organization_role=row.organization_role,
        workspace_role=row.workspace_role,
    )
