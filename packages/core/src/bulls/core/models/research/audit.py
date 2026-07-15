"""Append-only audit records for access to private institutional research."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class ResearchAuditEvent(Base):
    """One immutable security or workflow event within an organization workspace."""

    __tablename__ = "research_audit_events"
    __table_args__ = (
        CheckConstraint("event_type <> ''", name="ck_research_audit_events_event_type"),
        CheckConstraint("resource_type <> ''", name="ck_research_audit_events_resource_type"),
        CheckConstraint("resource_id <> ''", name="ck_research_audit_events_resource_id"),
        ForeignKeyConstraint(
            ["workspace_id", "organization_id", "tenant_id", "market"],
            [
                "research_workspaces.id",
                "research_workspaces.organization_id",
                "research_workspaces.tenant_id",
                "research_workspaces.market",
            ],
            name="fk_research_audit_events_workspace_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_user_id", "tenant_id", "market"],
            [
                "research_organization_memberships.organization_id",
                "research_organization_memberships.user_id",
                "research_organization_memberships.tenant_id",
                "research_organization_memberships.market",
            ],
            name="fk_research_audit_events_actor_scope",
            ondelete="CASCADE",
        ),
        Index(
            "ix_research_audit_events_workspace_occurred",
            "workspace_id",
            "occurred_at",
        ),
        Index(
            "ix_research_audit_events_org_actor_occurred",
            "organization_id",
            "actor_user_id",
            "occurred_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    actor_user_id: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(48))
    resource_id: Mapped[str] = mapped_column(String(160))
    request_id: Mapped[str | None] = mapped_column(String(128))
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    occurred_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
