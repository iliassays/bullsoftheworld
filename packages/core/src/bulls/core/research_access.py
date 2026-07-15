"""Fail-closed authorization policy for institutional research workspaces."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ResearchPermission(StrEnum):
    VIEW_WORKSPACE = "view_workspace"
    RUN_RESEARCH = "run_research"
    MANAGE_HYPOTHESES = "manage_hypotheses"
    MANAGE_RISK = "manage_risk"
    MANAGE_WORKSPACE = "manage_workspace"
    MANAGE_MEMBERS = "manage_members"
    MANAGE_ORGANIZATION = "manage_organization"
    MANAGE_BILLING = "manage_billing"


class OrganizationRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class WorkspaceRole(StrEnum):
    PORTFOLIO_MANAGER = "portfolio_manager"
    ANALYST = "analyst"
    RISK = "risk"
    VIEWER = "viewer"


@dataclass(frozen=True, slots=True)
class ResearchAccessContext:
    organization_status: str | None
    organization_membership_status: str | None
    organization_role: str | None
    workspace_status: str | None
    workspace_membership_status: str | None
    workspace_role: str | None


@dataclass(frozen=True, slots=True)
class ResearchAccessDecision:
    allowed: bool
    reason: str


_ORG_ADMIN_PERMISSIONS = frozenset(
    {
        ResearchPermission.VIEW_WORKSPACE,
        ResearchPermission.RUN_RESEARCH,
        ResearchPermission.MANAGE_HYPOTHESES,
        ResearchPermission.MANAGE_RISK,
        ResearchPermission.MANAGE_WORKSPACE,
        ResearchPermission.MANAGE_MEMBERS,
        ResearchPermission.MANAGE_ORGANIZATION,
    }
)

_WORKSPACE_PERMISSIONS: dict[WorkspaceRole, frozenset[ResearchPermission]] = {
    WorkspaceRole.PORTFOLIO_MANAGER: frozenset(
        {
            ResearchPermission.VIEW_WORKSPACE,
            ResearchPermission.RUN_RESEARCH,
            ResearchPermission.MANAGE_HYPOTHESES,
            ResearchPermission.MANAGE_RISK,
            ResearchPermission.MANAGE_WORKSPACE,
            ResearchPermission.MANAGE_MEMBERS,
        }
    ),
    WorkspaceRole.ANALYST: frozenset(
        {
            ResearchPermission.VIEW_WORKSPACE,
            ResearchPermission.RUN_RESEARCH,
            ResearchPermission.MANAGE_HYPOTHESES,
        }
    ),
    WorkspaceRole.RISK: frozenset(
        {
            ResearchPermission.VIEW_WORKSPACE,
            ResearchPermission.RUN_RESEARCH,
            ResearchPermission.MANAGE_RISK,
        }
    ),
    WorkspaceRole.VIEWER: frozenset({ResearchPermission.VIEW_WORKSPACE}),
}


def evaluate_research_access(
    context: ResearchAccessContext,
    permission: ResearchPermission | str,
) -> ResearchAccessDecision:
    """Evaluate one permission without trusting caller-provided organization identifiers.

    Values normally come from a single database query anchored on ``workspace_id``. Any missing or
    unknown role/status is denied, which keeps future schema additions from accidentally granting
    access before the policy is updated.
    """

    try:
        resolved_permission = ResearchPermission(permission)
    except (TypeError, ValueError):
        return ResearchAccessDecision(False, "unknown_permission")

    if context.organization_status != "active":
        return ResearchAccessDecision(False, "organization_inactive")
    if context.organization_membership_status != "active":
        return ResearchAccessDecision(False, "organization_membership_inactive")
    if context.workspace_status != "active":
        return ResearchAccessDecision(False, "workspace_inactive")

    try:
        organization_role = OrganizationRole(context.organization_role or "")
    except ValueError:
        return ResearchAccessDecision(False, "unknown_organization_role")

    if organization_role is OrganizationRole.OWNER:
        return ResearchAccessDecision(True, "organization_owner")
    if organization_role is OrganizationRole.ADMIN:
        allowed = resolved_permission in _ORG_ADMIN_PERMISSIONS
        return ResearchAccessDecision(allowed, "organization_admin" if allowed else "owner_only")

    if context.workspace_membership_status != "active":
        return ResearchAccessDecision(False, "workspace_membership_inactive")
    try:
        workspace_role = WorkspaceRole(context.workspace_role or "")
    except ValueError:
        return ResearchAccessDecision(False, "unknown_workspace_role")

    allowed = resolved_permission in _WORKSPACE_PERMISSIONS[workspace_role]
    return ResearchAccessDecision(allowed, "workspace_role" if allowed else "insufficient_role")
