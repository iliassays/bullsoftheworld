"""Auditable cohort onboarding decisions for large market universes."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
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
