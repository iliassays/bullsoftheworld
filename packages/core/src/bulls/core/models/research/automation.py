"""Tenant-bound automation policy for the Atlas research lifecycle."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class ResearchAutomationPolicy(Base):
    """One bounded, auditable lifecycle policy per private workspace."""

    __tablename__ = "research_automation_policies"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_automation_policies_security_scope",
        ),
        UniqueConstraint("workspace_id", name="uq_research_automation_policies_workspace"),
        CheckConstraint(
            "queue_limit >= 1 AND queue_limit <= 50",
            name="ck_research_automation_policies_queue_limit",
        ),
        CheckConstraint(
            "research_limit >= 1 AND research_limit <= queue_limit",
            name="ck_research_automation_policies_research_limit",
        ),
        CheckConstraint(
            "universe_limit >= 5 AND universe_limit <= 30",
            name="ck_research_automation_policies_universe_limit",
        ),
        CheckConstraint(
            "initial_capital > 0",
            name="ck_research_automation_policies_initial_capital",
        ),
        CheckConstraint(
            "cap_tier IS NULL OR cap_tier IN ('mega', 'large', 'mid', 'small', 'micro', 'penny')",
            name="ck_research_automation_policies_cap_tier",
        ),
        CheckConstraint(
            "strategy_key IN ('dse_reversal_v1', 'us_breakout_v1')",
            name="ck_research_automation_policies_strategy",
        ),
        CheckConstraint(
            "last_run_status IS NULL OR last_run_status IN "
            "('queued', 'running', 'succeeded', 'failed')",
            name="ck_research_automation_policies_last_status",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "organization_id", "tenant_id", "market"],
            [
                "research_workspaces.id",
                "research_workspaces.organization_id",
                "research_workspaces.tenant_id",
                "research_workspaces.market",
            ],
            name="fk_research_automation_policies_workspace",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "requested_by_user_id", "tenant_id", "market"],
            [
                "research_organization_memberships.organization_id",
                "research_organization_memberships.user_id",
                "research_organization_memberships.tenant_id",
                "research_organization_memberships.market",
            ],
            name="fk_research_automation_policies_requester",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_research_automation_policies_workspace_enabled",
            "workspace_id",
            "enabled",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    requested_by_user_id: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    queue_limit: Mapped[int] = mapped_column(Integer, default=20, server_default="20")
    research_limit: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    cap_tier: Mapped[str | None] = mapped_column(String(16))
    strategy_key: Mapped[str] = mapped_column(String(48))
    universe_limit: Mapped[int] = mapped_column(Integer, default=25, server_default="25")
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    next_run_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_status: Mapped[str | None] = mapped_column(String(16))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
