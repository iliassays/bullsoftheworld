from __future__ import annotations

import pytest

from bulls.core.research_access import (
    ResearchAccessContext,
    ResearchPermission,
    evaluate_research_access,
)


def _context(
    *,
    organization_status: str | None = "active",
    organization_membership_status: str | None = "active",
    organization_role: str | None = "member",
    workspace_status: str | None = "active",
    workspace_membership_status: str | None = "active",
    workspace_role: str | None = "viewer",
) -> ResearchAccessContext:
    return ResearchAccessContext(
        organization_status=organization_status,
        organization_membership_status=organization_membership_status,
        organization_role=organization_role,
        workspace_status=workspace_status,
        workspace_membership_status=workspace_membership_status,
        workspace_role=workspace_role,
    )


@pytest.mark.parametrize(
    ("role", "allowed", "denied"),
    [
        (
            "portfolio_manager",
            ResearchPermission.MANAGE_WORKSPACE,
            ResearchPermission.MANAGE_ORGANIZATION,
        ),
        (
            "analyst",
            ResearchPermission.MANAGE_HYPOTHESES,
            ResearchPermission.MANAGE_RISK,
        ),
        (
            "risk",
            ResearchPermission.MANAGE_RISK,
            ResearchPermission.MANAGE_HYPOTHESES,
        ),
        (
            "viewer",
            ResearchPermission.VIEW_WORKSPACE,
            ResearchPermission.RUN_RESEARCH,
        ),
    ],
)
def test_workspace_roles_follow_least_privilege(
    role: str,
    allowed: ResearchPermission,
    denied: ResearchPermission,
) -> None:
    context = _context(workspace_role=role)

    assert evaluate_research_access(context, allowed).allowed
    assert not evaluate_research_access(context, denied).allowed


def test_organization_admin_cannot_manage_billing() -> None:
    context = _context(
        organization_role="admin",
        workspace_membership_status=None,
        workspace_role=None,
    )

    assert evaluate_research_access(context, ResearchPermission.MANAGE_WORKSPACE).allowed
    decision = evaluate_research_access(context, ResearchPermission.MANAGE_BILLING)
    assert not decision.allowed
    assert decision.reason == "owner_only"


def test_owner_has_explicit_permissions_but_not_unknown_future_permissions() -> None:
    context = _context(
        organization_role="owner",
        workspace_membership_status=None,
        workspace_role=None,
    )

    assert evaluate_research_access(context, ResearchPermission.MANAGE_BILLING).allowed
    decision = evaluate_research_access(context, "delete_everything")
    assert not decision.allowed
    assert decision.reason == "unknown_permission"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"organization_status": "suspended"}, "organization_inactive"),
        (
            {"organization_membership_status": "disabled"},
            "organization_membership_inactive",
        ),
        ({"workspace_status": "archived"}, "workspace_inactive"),
        (
            {"workspace_membership_status": "disabled"},
            "workspace_membership_inactive",
        ),
        ({"organization_role": "future_role"}, "unknown_organization_role"),
        ({"workspace_role": "future_role"}, "unknown_workspace_role"),
    ],
)
def test_inactive_or_unknown_access_state_fails_closed(
    overrides: dict[str, str],
    reason: str,
) -> None:
    decision = evaluate_research_access(
        _context(**overrides),
        ResearchPermission.VIEW_WORKSPACE,
    )

    assert not decision.allowed
    assert decision.reason == reason
