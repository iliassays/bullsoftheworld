from __future__ import annotations

import uuid

from api.institutional_research.audit import record_research_audit_event
from bulls.core.models import ResearchAuditEvent, ResearchWorkspace


class _Session:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)


def test_audit_writer_copies_security_scope_from_authorized_workspace() -> None:
    workspace = ResearchWorkspace(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        tenant_id="bullsofwallst",
        market="US",
        slug="core-equity",
        name="Core equity",
        status="active",
        base_currency="USD",
        created_by_user_id=17,
    )
    session = _Session()

    event = record_research_audit_event(
        session,  # type: ignore[arg-type]
        workspace=workspace,
        actor_user_id=17,
        event_type="company_dossier_viewed",
        resource_type="security",
        resource_id="US:NXTC",
        request_id="request-123",
    )

    assert session.added == [event]
    assert isinstance(event, ResearchAuditEvent)
    assert event.organization_id == workspace.organization_id
    assert event.workspace_id == workspace.id
    assert event.tenant_id == "bullsofwallst"
    assert event.market == "US"
    assert event.actor_user_id == 17
