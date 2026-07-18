"""Tenant-isolated Atlas shadow portfolios and forward outcome observations."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class ResearchShadowPortfolio(Base):
    __tablename__ = "research_shadow_portfolios"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_shadow_portfolios_security_scope",
        ),
        UniqueConstraint(
            "id",
            "workspace_id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_shadow_portfolios_accounting_scope",
        ),
        UniqueConstraint(
            "workspace_id", "name", name="uq_research_shadow_portfolios_workspace_name"
        ),
        CheckConstraint(
            "status IN ('active', 'paused', 'archived')",
            name="ck_research_shadow_portfolios_status",
        ),
        CheckConstraint(
            "initial_capital > 0", name="ck_research_shadow_portfolios_initial_capital"
        ),
        ForeignKeyConstraint(
            ["workspace_id", "organization_id", "tenant_id", "market"],
            [
                "research_workspaces.id",
                "research_workspaces.organization_id",
                "research_workspaces.tenant_id",
                "research_workspaces.market",
            ],
            name="fk_research_shadow_portfolios_workspace",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["source_run_id", "organization_id", "tenant_id", "market"],
            [
                "research_runs.id",
                "research_runs.organization_id",
                "research_runs.tenant_id",
                "research_runs.market",
            ],
            name="fk_research_shadow_portfolios_source_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by_user_id", "tenant_id", "market"],
            [
                "research_organization_memberships.organization_id",
                "research_organization_memberships.user_id",
                "research_organization_memberships.tenant_id",
                "research_organization_memberships.market",
            ],
            name="fk_research_shadow_portfolios_creator",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_research_shadow_portfolios_workspace_status",
            "workspace_id",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    source_run_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_by_user_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(120))
    strategy_key: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    inception_date: Mapped[dt.date] = mapped_column(Date)
    last_evaluated_on: Mapped[dt.date | None] = mapped_column(Date)
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ResearchShadowSnapshot(Base):
    __tablename__ = "research_shadow_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_shadow_snapshots_security_scope",
        ),
        UniqueConstraint(
            "portfolio_id", "as_of_date", name="uq_research_shadow_snapshots_portfolio_date"
        ),
        ForeignKeyConstraint(
            ["portfolio_id", "organization_id", "tenant_id", "market"],
            [
                "research_shadow_portfolios.id",
                "research_shadow_portfolios.organization_id",
                "research_shadow_portfolios.tenant_id",
                "research_shadow_portfolios.market",
            ],
            name="fk_research_shadow_snapshots_portfolio",
            ondelete="CASCADE",
        ),
        CheckConstraint("session_number >= 0", name="ck_research_shadow_snapshots_session_number"),
        CheckConstraint(
            "nav > 0 AND benchmark_nav > 0 AND peak_nav > 0",
            name="ck_research_shadow_snapshots_positive_nav",
        ),
        CheckConstraint(
            "cash >= 0 AND cumulative_fees >= 0 AND cumulative_turnover >= 0",
            name="ck_research_shadow_snapshots_non_negative_values",
        ),
        CheckConstraint(
            "gross_exposure_pct >= 0 AND gross_exposure_pct <= 100 "
            "AND drawdown_pct >= 0 AND drawdown_pct <= 100",
            name="ck_research_shadow_snapshots_bounded_percentages",
        ),
        Index(
            "ix_research_shadow_snapshots_portfolio_date",
            "portfolio_id",
            "as_of_date",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    as_of_date: Mapped[dt.date] = mapped_column(Date)
    session_number: Mapped[int] = mapped_column(Integer)
    nav: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    cash: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    benchmark_nav: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    peak_nav: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    gross_exposure_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    drawdown_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    cumulative_fees: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    cumulative_turnover: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    positions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    pending_settlements: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    target_weights: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    trades: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    risk_interventions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ResearchOutcomeObservation(Base):
    __tablename__ = "research_outcome_observations"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_outcome_observations_security_scope",
        ),
        UniqueConstraint("run_id", "horizon_sessions", name="uq_research_outcomes_run_horizon"),
        CheckConstraint(
            "status IN ('pending', 'matured', 'unavailable')",
            name="ck_research_outcomes_status",
        ),
        CheckConstraint("horizon_sessions IN (5, 20, 60)", name="ck_research_outcomes_horizon"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_research_outcomes_confidence"
        ),
        CheckConstraint("reference_price > 0", name="ck_research_outcomes_reference_price"),
        ForeignKeyConstraint(
            ["workspace_id", "organization_id", "tenant_id", "market"],
            [
                "research_workspaces.id",
                "research_workspaces.organization_id",
                "research_workspaces.tenant_id",
                "research_workspaces.market",
            ],
            name="fk_research_outcomes_workspace",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["run_id", "organization_id", "tenant_id", "market"],
            [
                "research_runs.id",
                "research_runs.organization_id",
                "research_runs.tenant_id",
                "research_runs.market",
            ],
            name="fk_research_outcomes_run",
            ondelete="CASCADE",
        ),
        Index(
            "ix_research_outcomes_workspace_status_horizon",
            "workspace_id",
            "status",
            "horizon_sessions",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    code: Mapped[str] = mapped_column(String(32))
    signal_status: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    reference_date: Mapped[dt.date] = mapped_column(Date)
    reference_price: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    horizon_sessions: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    outcome_date: Mapped[dt.date | None] = mapped_column(Date)
    outcome_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    return_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    max_adverse_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    max_favorable_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
