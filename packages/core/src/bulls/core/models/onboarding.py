"""Auditable cohort onboarding decisions for large market universes."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
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


class UniverseOnboardingRun(Base):
    __tablename__ = "universe_onboarding_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_universe_onboarding_run_status",
        ),
        Index(
            "uq_universe_onboarding_runs_active_manifest",
            "manifest_sha256",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    market: Mapped[str] = mapped_column(String(8), index=True)
    cohort_name: Mapped[str] = mapped_column(String(96))
    cohort_version: Mapped[str] = mapped_column(String(32))
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), index=True)
    promotion_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    requested_count: Mapped[int] = mapped_column(Integer)
    passed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class UniverseOnboardingResult(Base):
    __tablename__ = "universe_onboarding_results"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('passed', 'failed')",
            name="ck_universe_onboarding_result_decision",
        ),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("universe_onboarding_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    market: Mapped[str] = mapped_column(String(8))
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    security_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("security_master.security_id"),
    )
    decision: Mapped[str] = mapped_column(String(16), index=True)
    required_gates_passed: Mapped[bool] = mapped_column(Boolean)
    gates: Mapped[dict[str, Any]] = mapped_column(JSONB)
    failure_reasons: Mapped[list[str]] = mapped_column(JSONB)
    bar_count: Mapped[int] = mapped_column(Integer)
    first_bar_date: Mapped[dt.date | None] = mapped_column(Date)
    last_bar_date: Mapped[dt.date | None] = mapped_column(Date)
    adjusted_close_ratio: Mapped[float | None] = mapped_column(Float)
    nonzero_volume_ratio: Mapped[float | None] = mapped_column(Float)
    sec_filings_count: Mapped[int] = mapped_column(Integer)
    sec_facts_count: Mapped[int] = mapped_column(Integer)
    has_13f: Mapped[bool] = mapped_column(Boolean)
    evaluated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UniverseOnboardingStage(Base):
    """Durable checkpoint for one idempotent acquisition stage within an onboarding run."""

    __tablename__ = "universe_onboarding_stages"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_universe_onboarding_stage_status",
        ),
        CheckConstraint(
            "input_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_universe_onboarding_stage_input_hash",
        ),
        CheckConstraint(
            "output_fingerprint IS NULL OR output_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_universe_onboarding_stage_output_hash",
        ),
        UniqueConstraint("run_id", "stage_key", name="uq_universe_onboarding_stages_run_stage"),
        Index("ix_universe_onboarding_stages_run_ordinal", "run_id", "ordinal"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("universe_onboarding_runs.id", ondelete="CASCADE"),
    )
    stage_key: Mapped[str] = mapped_column(String(48))
    ordinal: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    attempts: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    output_fingerprint: Mapped[str | None] = mapped_column(String(64))
    stats: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class OnDemandResearchJob(Base):
    """One deduplicated market-level preparation job per security."""

    __tablename__ = "on_demand_research_jobs"
    __table_args__ = (
        UniqueConstraint("market", "code", name="uq_on_demand_research_job_market_code"),
        CheckConstraint(
            "status IN ('queued', 'running', 'review_required', 'ready', 'rejected', 'failed')",
            name="ck_on_demand_research_job_status",
        ),
        Index("ix_on_demand_research_job_status_requested", "status", "requested_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    market: Mapped[str] = mapped_column(String(8))
    code: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24))
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("universe_onboarding_runs.id", ondelete="SET NULL"),
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    request_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    requested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class OnDemandResearchRequest(Base):
    """Tenant/user audit record used for quotas without duplicating preparation work."""

    __tablename__ = "on_demand_research_requests"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "market",
            "code",
            "request_date",
            name="uq_on_demand_research_request_user_symbol_day",
        ),
        Index(
            "ix_on_demand_research_request_user_date",
            "tenant_id",
            "user_id",
            "request_date",
        ),
        ForeignKeyConstraint(
            ["user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_on_demand_research_requests_user_tenant",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("on_demand_research_jobs.id", ondelete="CASCADE"),
        index=True,
    )
    tenant_id: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(Integer)
    market: Mapped[str] = mapped_column(String(8))
    code: Mapped[str] = mapped_column(String(16))
    request_date: Mapped[dt.date] = mapped_column(Date)
    requested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
