"""Small append-only audit writer for private research workflows."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bulls.core.models import ResearchAuditEvent, ResearchWorkspace


def record_research_audit_event(
    session: AsyncSession,
    *,
    workspace: ResearchWorkspace,
    actor_user_id: int,
    event_type: str,
    resource_type: str,
    resource_id: str,
    request_id: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> ResearchAuditEvent:
    """Stage an audit event in the same transaction as the authorized request."""

    event = ResearchAuditEvent(
        id=uuid.uuid4(),
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        tenant_id=workspace.tenant_id,
        market=workspace.market,
        actor_user_id=actor_user_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id,
        attributes=attributes or {},
    )
    session.add(event)
    return event
