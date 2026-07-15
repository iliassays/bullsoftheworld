"""Durable, reproducible research workflow runs and execution steps."""

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
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class ResearchRun(Base):
    __tablename__ = "research_runs"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_runs_security_scope",
        ),
        UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_research_runs_workspace_idempotency_key",
        ),
        CheckConstraint(
            "run_kind IN "
            "('dossier', 'deep_research', 'hypothesis', 'monitor', 'portfolio', 'lifecycle')",
            name="ck_research_runs_kind",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_research_runs_status",
        ),
        CheckConstraint(
            "idempotency_key <> ''",
            name="ck_research_runs_idempotency_key",
        ),
        CheckConstraint(
            "code_version <> ''",
            name="ck_research_runs_code_version",
        ),
        CheckConstraint(
            "evidence_snapshot_hash IS NULL OR evidence_snapshot_hash ~ '^[0-9a-f]{64}$'",
            name="ck_research_runs_evidence_snapshot_hash",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "organization_id", "tenant_id", "market"],
            [
                "research_workspaces.id",
                "research_workspaces.organization_id",
                "research_workspaces.tenant_id",
                "research_workspaces.market",
            ],
            name="fk_research_runs_workspace",
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
            name="fk_research_runs_requester_membership",
            ondelete="RESTRICT",
        ),
        Index("ix_research_runs_workspace_requested", "workspace_id", "requested_at"),
        Index(
            "ix_research_runs_tenant_organization_status",
            "tenant_id",
            "organization_id",
            "status",
        ),
        Index("ix_research_runs_security_cutoff", "market", "code", "knowledge_cutoff_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tenant_id: Mapped[str] = mapped_column(String(64))
    requested_by_user_id: Mapped[int] = mapped_column(Integer)
    run_kind: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16), default="queued", server_default="queued")
    question: Mapped[str] = mapped_column(Text)
    market: Mapped[str] = mapped_column(String(8))
    code: Mapped[str | None] = mapped_column(String(32))
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    idempotency_key: Mapped[str] = mapped_column(String(96))
    knowledge_cutoff_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(96))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    code_version: Mapped[str] = mapped_column(String(64))
    evidence_snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    requested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)


class ResearchRunStep(Base):
    __tablename__ = "research_run_steps"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_run_steps_security_scope",
        ),
        UniqueConstraint("run_id", "ordinal", name="uq_research_run_steps_run_ordinal"),
        CheckConstraint("ordinal >= 0", name="ck_research_run_steps_ordinal"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'skipped')",
            name="ck_research_run_steps_status",
        ),
        ForeignKeyConstraint(
            ["run_id", "organization_id", "tenant_id", "market"],
            [
                "research_runs.id",
                "research_runs.organization_id",
                "research_runs.tenant_id",
                "research_runs.market",
            ],
            name="fk_research_run_steps_run",
            ondelete="CASCADE",
        ),
        Index("ix_research_run_steps_run_status", "run_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    ordinal: Mapped[int] = mapped_column(Integer)
    step_kind: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(16), default="queued", server_default="queued")
    input_hash: Mapped[str | None] = mapped_column(String(64))
    output: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
