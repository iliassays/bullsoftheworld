"""Versioned Atlas condition evidence, calibration, and opt-in subscriptions.

Condition transitions and calibration are shared market evidence, like daily bars. User
subscriptions are tenant-isolated preferences and never create strategy targets or orders.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class ResearchConditionTransition(Base):
    """Append-only classification change with outcomes matured in place."""

    __tablename__ = "research_condition_transitions"
    __table_args__ = (
        CheckConstraint(
            "state IN ('observed', 'not_observed', 'unavailable')",
            name="ck_research_condition_transitions_state",
        ),
        CheckConstraint(
            "previous_state IS NULL OR previous_state IN "
            "('observed', 'not_observed', 'unavailable')",
            name="ck_research_condition_transitions_previous_state",
        ),
        CheckConstraint(
            "evidence_mode IN ('forward', 'reconstructed')",
            name="ck_research_condition_transitions_evidence_mode",
        ),
        CheckConstraint(
            "reference_close > 0", name="ck_research_condition_transitions_reference_close"
        ),
        ForeignKeyConstraint(
            ["market", "code"],
            ["symbols.market", "symbols.code"],
            name="fk_research_condition_transitions_symbol",
            ondelete="CASCADE",
        ),
        Index(
            "ix_research_condition_transitions_market_condition_date",
            "market",
            "condition_key",
            "as_of_date",
        ),
        Index(
            "ix_research_condition_transitions_market_code_condition",
            "market",
            "code",
            "condition_key",
            "as_of_date",
        ),
    )

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    condition_key: Mapped[str] = mapped_column(String(48), primary_key=True)
    condition_version: Mapped[str] = mapped_column(String(24), primary_key=True)
    methodology_version: Mapped[str] = mapped_column(String(48), primary_key=True)
    as_of_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    state: Mapped[str] = mapped_column(String(16))
    previous_state: Mapped[str | None] = mapped_column(String(16))
    reference_close: Mapped[float] = mapped_column(Float)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    outcomes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    evidence_mode: Mapped[str] = mapped_column(
        String(16), default="forward", server_default="forward"
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ResearchConditionCalibration(Base):
    """Latest market-level diagnostic aggregate for one version and horizon."""

    __tablename__ = "research_condition_calibrations"
    __table_args__ = (
        CheckConstraint(
            "evidence_mode IN ('forward', 'reconstructed')",
            name="ck_research_condition_calibrations_evidence_mode",
        ),
        CheckConstraint(
            "horizon_sessions IN (1, 5, 20, 60)",
            name="ck_research_condition_calibrations_horizon",
        ),
        CheckConstraint(
            "observations >= 0 AND matured >= 0 AND pending >= 0 "
            "AND observations = matured + pending AND universe_size >= 0",
            name="ck_research_condition_calibrations_counts",
        ),
        Index(
            "ix_research_condition_calibrations_market_date",
            "market",
            "as_of_date",
        ),
    )

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    condition_key: Mapped[str] = mapped_column(String(48), primary_key=True)
    condition_version: Mapped[str] = mapped_column(String(24), primary_key=True)
    methodology_version: Mapped[str] = mapped_column(String(48), primary_key=True)
    evidence_mode: Mapped[str] = mapped_column(String(16), primary_key=True)
    horizon_sessions: Mapped[int] = mapped_column(Integer, primary_key=True)
    as_of_date: Mapped[dt.date] = mapped_column(Date)
    history_start_date: Mapped[dt.date | None] = mapped_column(Date)
    observations: Mapped[int] = mapped_column(Integer)
    matured: Mapped[int] = mapped_column(Integer)
    pending: Mapped[int] = mapped_column(Integer)
    average_return_pct: Mapped[float | None] = mapped_column(Float)
    median_return_pct: Mapped[float | None] = mapped_column(Float)
    positive_rate_pct: Mapped[float | None] = mapped_column(Float)
    average_benchmark_return_pct: Mapped[float | None] = mapped_column(Float)
    median_excess_return_pct: Mapped[float | None] = mapped_column(Float)
    benchmark_observations: Mapped[int] = mapped_column(Integer)
    average_max_favorable_pct: Mapped[float | None] = mapped_column(Float)
    average_max_adverse_pct: Mapped[float | None] = mapped_column(Float)
    universe_size: Mapped[int] = mapped_column(Integer)
    point_in_time_complete: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    warning_text: Mapped[str | None] = mapped_column(String(500))
    computed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ResearchConditionSubscription(Base):
    """Explicit per-user request for a future condition-observation alert."""

    __tablename__ = "atlas_condition_subscriptions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_atlas_condition_subscriptions_user_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["market", "code"],
            ["symbols.market", "symbols.code"],
            name="fk_atlas_condition_subscriptions_symbol",
            ondelete="CASCADE",
        ),
        Index(
            "ix_atlas_condition_subscriptions_dispatch",
            "tenant_id",
            "market",
            "code",
            "condition_key",
            "enabled",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    condition_key: Mapped[str] = mapped_column(String(48), primary_key=True)
    condition_version: Mapped[str] = mapped_column(String(24), primary_key=True)
    methodology_version: Mapped[str] = mapped_column(String(48), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_alerted_on: Mapped[dt.date | None] = mapped_column(Date)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
