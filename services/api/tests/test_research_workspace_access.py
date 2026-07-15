from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from api.research_access import (
    ResearchAccessDenied,
    ResearchWorkspaceNotFound,
    authorize_research_workspace,
)
from bulls.core.models import ResearchWorkspace
from bulls.core.research_access import ResearchPermission


@dataclass
class _AccessRow:
    workspace: ResearchWorkspace
    organization_status: str | None = "active"
    organization_membership_status: str | None = "active"
    organization_role: str | None = "member"
    workspace_membership_status: str | None = "active"
    workspace_role: str | None = "viewer"

    def __getitem__(self, index: int) -> ResearchWorkspace:
        if index != 0:
            raise IndexError(index)
        return self.workspace


class _Result:
    def __init__(self, row: _AccessRow | None) -> None:
        self.row = row

    def one_or_none(self) -> _AccessRow | None:
        return self.row


class _Session:
    def __init__(self, row: _AccessRow | None) -> None:
        self.row = row
        self.statement: Any = None

    async def execute(self, statement: Any) -> _Result:
        self.statement = statement
        return _Result(self.row)


def _workspace() -> ResearchWorkspace:
    return ResearchWorkspace(
        organization_id=uuid.uuid4(),
        tenant_id="bullsofwallst",
        market="US",
        slug="core-research",
        name="Core Research",
        status="active",
        base_currency="USD",
        created_by_user_id=1,
    )


@pytest.mark.asyncio
async def test_outsider_cannot_discover_a_private_workspace() -> None:
    session = _Session(
        _AccessRow(
            workspace=_workspace(),
            organization_membership_status=None,
            organization_role=None,
            workspace_membership_status=None,
            workspace_role=None,
        )
    )

    with pytest.raises(ResearchWorkspaceNotFound):
        await authorize_research_workspace(
            session,  # type: ignore[arg-type]
            workspace_id=uuid.uuid4(),
            user_id=99,
            tenant_id="bullsofwallst",
            market="US",
            permission=ResearchPermission.VIEW_WORKSPACE,
        )


@pytest.mark.asyncio
async def test_organization_member_cannot_discover_an_unassigned_workspace() -> None:
    session = _Session(
        _AccessRow(
            workspace=_workspace(),
            workspace_membership_status=None,
            workspace_role=None,
        )
    )

    with pytest.raises(ResearchWorkspaceNotFound):
        await authorize_research_workspace(
            session,  # type: ignore[arg-type]
            workspace_id=uuid.uuid4(),
            user_id=2,
            tenant_id="bullsofwallst",
            market="US",
            permission=ResearchPermission.VIEW_WORKSPACE,
        )


@pytest.mark.asyncio
async def test_viewer_is_denied_research_execution_with_a_stable_reason() -> None:
    session = _Session(_AccessRow(workspace=_workspace()))

    with pytest.raises(ResearchAccessDenied) as exc:
        await authorize_research_workspace(
            session,  # type: ignore[arg-type]
            workspace_id=uuid.uuid4(),
            user_id=3,
            tenant_id="bullsofwallst",
            market="US",
            permission=ResearchPermission.RUN_RESEARCH,
        )

    assert exc.value.reason == "insufficient_role"


@pytest.mark.asyncio
async def test_organization_owner_administers_workspace_without_local_membership() -> None:
    workspace = _workspace()
    session = _Session(
        _AccessRow(
            workspace=workspace,
            organization_role="owner",
            workspace_membership_status=None,
            workspace_role=None,
        )
    )

    authorized = await authorize_research_workspace(
        session,  # type: ignore[arg-type]
        workspace_id=uuid.uuid4(),
        user_id=1,
        tenant_id="bullsofwallst",
        market="US",
        permission=ResearchPermission.MANAGE_WORKSPACE,
    )

    assert authorized.workspace is workspace
    assert session.statement is not None


@pytest.mark.asyncio
async def test_workspace_from_another_market_is_rejected_even_if_a_row_is_returned() -> None:
    session = _Session(_AccessRow(workspace=_workspace()))

    with pytest.raises(ResearchWorkspaceNotFound):
        await authorize_research_workspace(
            session,  # type: ignore[arg-type]
            workspace_id=uuid.uuid4(),
            user_id=1,
            tenant_id="bullsofdhaka",
            market="DSE",
            permission=ResearchPermission.VIEW_WORKSPACE,
        )
