"""Portfolio mandate, strategy trial, and decision-lineage persistence for Atlas."""

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
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class ResearchInvestmentMandate(Base):
    """One immutable version of a workspace's portfolio and risk authority."""

    __tablename__ = "research_investment_mandates"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_investment_mandates_security_scope",
        ),
        UniqueConstraint("workspace_id", "version", name="uq_research_investment_mandates_version"),
        CheckConstraint(
            "status IN ('active', 'superseded')",
            name="ck_research_investment_mandates_status",
        ),
        CheckConstraint("version >= 1", name="ck_research_investment_mandates_version"),
        CheckConstraint(
            "max_gross_exposure_pct > 0 AND max_gross_exposure_pct <= 100 "
            "AND min_cash_reserve_pct >= 0 AND min_cash_reserve_pct < 100 "
            "AND max_gross_exposure_pct + min_cash_reserve_pct <= 100 "
            "AND max_position_weight_pct > 0 AND max_position_weight_pct <= 100 "
            "AND max_position_weight_pct <= max_gross_exposure_pct "
            "AND max_sector_weight_pct > 0 AND max_sector_weight_pct <= 100 "
            "AND max_sector_weight_pct >= max_position_weight_pct "
            "AND max_adv_participation_pct > 0 AND max_adv_participation_pct <= 100 "
            "AND portfolio_drawdown_brake_pct > 0 AND portfolio_drawdown_brake_pct <= 100 "
            "AND stress_loss_limit_pct > 0 AND stress_loss_limit_pct <= 100",
            name="ck_research_investment_mandates_limits",
        ),
        CheckConstraint(
            "specification_hash ~ '^[0-9a-f]{64}$'",
            name="ck_research_investment_mandates_hash",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "organization_id", "tenant_id", "market"],
            [
                "research_workspaces.id",
                "research_workspaces.organization_id",
                "research_workspaces.tenant_id",
                "research_workspaces.market",
            ],
            name="fk_research_investment_mandates_workspace",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by_user_id", "tenant_id", "market"],
            [
                "research_organization_memberships.organization_id",
                "research_organization_memberships.user_id",
                "research_organization_memberships.tenant_id",
                "research_organization_memberships.market",
            ],
            name="fk_research_investment_mandates_creator",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_research_investment_mandates_workspace_status",
            "workspace_id",
            "status",
        ),
        Index(
            "uq_research_investment_mandates_active_workspace",
            "workspace_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    created_by_user_id: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    objective: Mapped[str] = mapped_column(Text)
    benchmark_key: Mapped[str] = mapped_column(String(64))
    max_gross_exposure_pct: Mapped[Decimal] = mapped_column(Numeric(7, 3))
    min_cash_reserve_pct: Mapped[Decimal] = mapped_column(Numeric(7, 3))
    max_position_weight_pct: Mapped[Decimal] = mapped_column(Numeric(7, 3))
    max_sector_weight_pct: Mapped[Decimal] = mapped_column(Numeric(7, 3))
    max_adv_participation_pct: Mapped[Decimal] = mapped_column(Numeric(7, 3))
    portfolio_drawdown_brake_pct: Mapped[Decimal] = mapped_column(Numeric(7, 3))
    stress_loss_limit_pct: Mapped[Decimal] = mapped_column(Numeric(7, 3))
    specification_hash: Mapped[str] = mapped_column(String(64))
    effective_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ResearchStrategyTrial(Base):
    """A frozen strategy specification and its visible evaluation outcome."""

    __tablename__ = "research_strategy_trials"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_strategy_trials_security_scope",
        ),
        UniqueConstraint("source_run_id", name="uq_research_strategy_trials_source_run"),
        CheckConstraint(
            "status IN ('registered', 'diagnostic', 'shadow', 'eligible', 'rejected', 'retired')",
            name="ck_research_strategy_trials_status",
        ),
        CheckConstraint(
            "registration_state IN ('preregistered', 'legacy_reconstructed')",
            name="ck_research_strategy_trials_registration_state",
        ),
        CheckConstraint("trial_sequence >= 1", name="ck_research_strategy_trials_sequence"),
        CheckConstraint(
            "multiple_testing_policy <> ''",
            name="ck_research_strategy_trials_multiple_testing_policy",
        ),
        CheckConstraint(
            "specification_hash ~ '^[0-9a-f]{64}$'",
            name="ck_research_strategy_trials_hash",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "organization_id", "tenant_id", "market"],
            [
                "research_workspaces.id",
                "research_workspaces.organization_id",
                "research_workspaces.tenant_id",
                "research_workspaces.market",
            ],
            name="fk_research_strategy_trials_workspace",
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
            name="fk_research_strategy_trials_source_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by_user_id", "tenant_id", "market"],
            [
                "research_organization_memberships.organization_id",
                "research_organization_memberships.user_id",
                "research_organization_memberships.tenant_id",
                "research_organization_memberships.market",
            ],
            name="fk_research_strategy_trials_creator",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_research_strategy_trials_workspace_status",
            "workspace_id",
            "status",
            "registered_at",
        ),
        UniqueConstraint(
            "workspace_id",
            "strategy_key",
            "trial_sequence",
            name="uq_research_strategy_trials_family_sequence",
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
    strategy_key: Mapped[str] = mapped_column(String(48))
    strategy_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="registered")
    registration_state: Mapped[str] = mapped_column(String(24))
    trial_sequence: Mapped[int] = mapped_column(Integer)
    multiple_testing_policy: Mapped[str] = mapped_column(String(64))
    economic_hypothesis: Mapped[str] = mapped_column(Text)
    specification: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    specification_hash: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    registered_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ResearchDecisionEvent(Base):
    """Append-only audit projection derived from an accepted shadow snapshot."""

    __tablename__ = "research_decision_events"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_decision_events_security_scope",
        ),
        UniqueConstraint("portfolio_id", "sequence", name="uq_research_decision_events_sequence"),
        UniqueConstraint("portfolio_id", "event_key", name="uq_research_decision_events_key"),
        CheckConstraint("sequence >= 0", name="ck_research_decision_events_sequence"),
        CheckConstraint(
            "event_type IN ('signal', 'target', 'order', 'rejection', 'fill', 'position', 'risk', 'outcome')",
            name="ck_research_decision_events_type",
        ),
        CheckConstraint(
            "event_state IN ('observed', 'intended', 'constrained', 'executed', 'open', 'closed', 'measured')",
            name="ck_research_decision_events_state",
        ),
        CheckConstraint("event_key <> ''", name="ck_research_decision_events_key"),
        CheckConstraint(
            "payload_hash ~ '^[0-9a-f]{64}$'",
            name="ck_research_decision_events_payload_hash",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "organization_id", "tenant_id", "market"],
            [
                "research_workspaces.id",
                "research_workspaces.organization_id",
                "research_workspaces.tenant_id",
                "research_workspaces.market",
            ],
            name="fk_research_decision_events_workspace",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["portfolio_id", "organization_id", "tenant_id", "market"],
            [
                "research_shadow_portfolios.id",
                "research_shadow_portfolios.organization_id",
                "research_shadow_portfolios.tenant_id",
                "research_shadow_portfolios.market",
            ],
            name="fk_research_decision_events_portfolio",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "organization_id", "tenant_id", "market"],
            [
                "research_shadow_snapshots.id",
                "research_shadow_snapshots.organization_id",
                "research_shadow_snapshots.tenant_id",
                "research_shadow_snapshots.market",
            ],
            name="fk_research_decision_events_snapshot",
            ondelete="CASCADE",
        ),
        Index(
            "ix_research_decision_events_workspace_recorded",
            "workspace_id",
            "recorded_at",
        ),
        Index(
            "ix_research_decision_events_portfolio_effective",
            "portfolio_id",
            "effective_date",
            "sequence",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    portfolio_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    sequence: Mapped[int] = mapped_column(Integer)
    event_key: Mapped[str] = mapped_column(String(160))
    caused_by_event_key: Mapped[str | None] = mapped_column(String(160))
    event_type: Mapped[str] = mapped_column(String(16))
    event_state: Mapped[str] = mapped_column(String(16))
    code: Mapped[str | None] = mapped_column(String(32))
    effective_date: Mapped[dt.date] = mapped_column(Date)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    payload_hash: Mapped[str] = mapped_column(String(64))
    recorded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ResearchAccountingEvent(Base):
    """Append-only event authority for paper cash, positions, fees, and settlement."""

    __tablename__ = "research_accounting_events"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_accounting_events_security_scope",
        ),
        UniqueConstraint("portfolio_id", "sequence", name="uq_research_accounting_events_sequence"),
        UniqueConstraint("portfolio_id", "event_key", name="uq_research_accounting_events_key"),
        CheckConstraint("sequence >= 0", name="ck_research_accounting_events_sequence"),
        CheckConstraint("session_number >= 0", name="ck_research_accounting_events_session_number"),
        CheckConstraint(
            "event_type IN ('opening_balance', 'methodology_boundary', "
            "'settlement_release', 'share_settlement_release', 'fill', 'valuation')",
            name="ck_research_accounting_events_type",
        ),
        CheckConstraint("event_key <> ''", name="ck_research_accounting_events_key"),
        CheckConstraint("engine_version <> ''", name="ck_research_accounting_events_engine"),
        CheckConstraint(
            "payload_hash ~ '^[0-9a-f]{64}$'",
            name="ck_research_accounting_events_payload_hash",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "organization_id", "tenant_id", "market"],
            [
                "research_workspaces.id",
                "research_workspaces.organization_id",
                "research_workspaces.tenant_id",
                "research_workspaces.market",
            ],
            name="fk_research_accounting_events_workspace",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["portfolio_id", "workspace_id", "organization_id", "tenant_id", "market"],
            [
                "research_shadow_portfolios.id",
                "research_shadow_portfolios.workspace_id",
                "research_shadow_portfolios.organization_id",
                "research_shadow_portfolios.tenant_id",
                "research_shadow_portfolios.market",
            ],
            name="fk_research_accounting_events_portfolio",
            ondelete="CASCADE",
        ),
        Index(
            "ix_research_accounting_events_workspace_recorded",
            "workspace_id",
            "recorded_at",
        ),
        Index(
            "ix_research_accounting_events_portfolio_effective",
            "portfolio_id",
            "effective_date",
            "sequence",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    portfolio_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    sequence: Mapped[int] = mapped_column(Integer)
    session_number: Mapped[int] = mapped_column(Integer)
    event_key: Mapped[str] = mapped_column(String(160))
    event_type: Mapped[str] = mapped_column(String(32))
    code: Mapped[str | None] = mapped_column(String(32))
    effective_date: Mapped[dt.date] = mapped_column(Date)
    engine_version: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    payload_hash: Mapped[str] = mapped_column(String(64))
    recorded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
