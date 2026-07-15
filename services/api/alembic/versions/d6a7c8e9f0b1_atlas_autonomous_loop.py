"""Add Atlas shadow portfolios and forward outcome calibration.

Revision ID: d6a7c8e9f0b1
Revises: c47e9a1b2d63
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d6a7c8e9f0b1"
down_revision = "c47e9a1b2d63"
branch_labels = None
depends_on = None

_USER_ID = "NULLIF(current_setting('app.research_user_id', true), '')::integer"
_TENANT_SCOPE = (
    "tenant_id = current_setting('app.research_tenant_id', true) "
    "AND market = current_setting('app.research_market', true)"
)


def _workspace_access(table: str) -> str:
    return (
        "EXISTS (SELECT 1 FROM research_organization_memberships rom "
        f"WHERE rom.organization_id = {table}.organization_id "
        f"AND rom.tenant_id = {table}.tenant_id AND rom.market = {table}.market "
        f"AND rom.user_id = {_USER_ID} AND rom.status = 'active' "
        "AND (rom.role IN ('owner', 'admin') OR EXISTS ("
        "SELECT 1 FROM research_workspace_memberships rwm "
        f"WHERE rwm.workspace_id = {table}.workspace_id "
        f"AND rwm.organization_id = {table}.organization_id "
        f"AND rwm.tenant_id = {table}.tenant_id AND rwm.market = {table}.market "
        f"AND rwm.user_id = {_USER_ID} AND rwm.status = 'active')))"
    )


def _json(name: str, *, array: bool = False) -> sa.Column:
    default = "'[]'::jsonb" if array else "'{}'::jsonb"
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text(default),
        nullable=False,
    )


def _enable_rls(table: str, predicate: str) -> None:
    policy = f"{table}_tenant_market_isolation"
    full = f"{_TENANT_SCOPE} AND ({predicate})"
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'CREATE POLICY "{policy}" ON "{table}" USING ({full}) WITH CHECK ({full})'))


def upgrade() -> None:
    op.create_table(
        "research_shadow_portfolios",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("source_run_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("strategy_key", sa.String(48), nullable=False),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("initial_capital", sa.Numeric(20, 4), nullable=False),
        sa.Column("inception_date", sa.Date(), nullable=False),
        sa.Column("last_evaluated_on", sa.Date(), nullable=True),
        _json("configuration"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'archived')",
            name="ck_research_shadow_portfolios_status",
        ),
        sa.CheckConstraint(
            "initial_capital > 0", name="ck_research_shadow_portfolios_initial_capital"
        ),
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_shadow_portfolios_security_scope",
        ),
        sa.UniqueConstraint(
            "workspace_id", "name", name="uq_research_shadow_portfolios_workspace_name"
        ),
    )
    op.create_index(
        "ix_research_shadow_portfolios_workspace_status",
        "research_shadow_portfolios",
        ["workspace_id", "status"],
    )

    op.create_table(
        "research_shadow_snapshots",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("session_number", sa.Integer(), nullable=False),
        sa.Column("nav", sa.Numeric(20, 4), nullable=False),
        sa.Column("cash", sa.Numeric(20, 4), nullable=False),
        sa.Column("benchmark_nav", sa.Numeric(20, 4), nullable=False),
        sa.Column("peak_nav", sa.Numeric(20, 4), nullable=False),
        sa.Column("gross_exposure_pct", sa.Numeric(10, 4), nullable=False),
        sa.Column("drawdown_pct", sa.Numeric(10, 4), nullable=False),
        sa.Column("cumulative_fees", sa.Numeric(20, 4), nullable=False),
        sa.Column("cumulative_turnover", sa.Numeric(20, 4), nullable=False),
        _json("positions"),
        _json("target_weights"),
        _json("trades", array=True),
        _json("risk_interventions", array=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
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
        sa.CheckConstraint(
            "session_number >= 0", name="ck_research_shadow_snapshots_session_number"
        ),
        sa.CheckConstraint(
            "nav > 0 AND benchmark_nav > 0 AND peak_nav > 0",
            name="ck_research_shadow_snapshots_positive_nav",
        ),
        sa.CheckConstraint(
            "cash >= 0 AND cumulative_fees >= 0 AND cumulative_turnover >= 0",
            name="ck_research_shadow_snapshots_non_negative_values",
        ),
        sa.CheckConstraint(
            "gross_exposure_pct >= 0 AND gross_exposure_pct <= 100 "
            "AND drawdown_pct >= 0 AND drawdown_pct <= 100",
            name="ck_research_shadow_snapshots_bounded_percentages",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_shadow_snapshots_security_scope",
        ),
        sa.UniqueConstraint(
            "portfolio_id", "as_of_date", name="uq_research_shadow_snapshots_portfolio_date"
        ),
    )
    op.create_index(
        "ix_research_shadow_snapshots_portfolio_date",
        "research_shadow_snapshots",
        ["portfolio_id", "as_of_date"],
    )

    op.create_table(
        "research_outcome_observations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("signal_status", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=False),
        sa.Column("reference_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("horizon_sessions", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("outcome_date", sa.Date(), nullable=True),
        sa.Column("outcome_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("return_pct", sa.Numeric(12, 6), nullable=True),
        sa.Column("max_adverse_pct", sa.Numeric(12, 6), nullable=True),
        sa.Column("max_favorable_pct", sa.Numeric(12, 6), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'matured', 'unavailable')", name="ck_research_outcomes_status"
        ),
        sa.CheckConstraint("horizon_sessions IN (5, 20, 60)", name="ck_research_outcomes_horizon"),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_research_outcomes_confidence"
        ),
        sa.CheckConstraint("reference_price > 0", name="ck_research_outcomes_reference_price"),
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_outcome_observations_security_scope",
        ),
        sa.UniqueConstraint("run_id", "horizon_sessions", name="uq_research_outcomes_run_horizon"),
    )
    op.create_index(
        "ix_research_outcomes_workspace_status_horizon",
        "research_outcome_observations",
        ["workspace_id", "status", "horizon_sessions"],
    )

    _enable_rls("research_shadow_portfolios", _workspace_access("research_shadow_portfolios"))
    _enable_rls(
        "research_shadow_snapshots",
        "EXISTS (SELECT 1 FROM research_shadow_portfolios rsp "
        "WHERE rsp.id = research_shadow_snapshots.portfolio_id "
        "AND rsp.organization_id = research_shadow_snapshots.organization_id "
        "AND rsp.tenant_id = research_shadow_snapshots.tenant_id "
        "AND rsp.market = research_shadow_snapshots.market)",
    )
    _enable_rls("research_outcome_observations", _workspace_access("research_outcome_observations"))


def downgrade() -> None:
    for table in (
        "research_outcome_observations",
        "research_shadow_snapshots",
        "research_shadow_portfolios",
    ):
        op.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_tenant_market_isolation" ON "{table}"'))
        op.drop_table(table)
