"""Add tenant-bound Atlas lifecycle automation policies.

Revision ID: e7b8c9d0a1f2
Revises: d6a7c8e9f0b1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e7b8c9d0a1f2"
down_revision = "d6a7c8e9f0b1"
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


def upgrade() -> None:
    op.drop_constraint("ck_research_runs_kind", "research_runs", type_="check")
    op.create_check_constraint(
        "ck_research_runs_kind",
        "research_runs",
        "run_kind IN "
        "('dossier', 'deep_research', 'hypothesis', 'monitor', 'portfolio', 'lifecycle')",
    )
    op.create_table(
        "research_automation_policies",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("queue_limit", sa.Integer(), server_default="20", nullable=False),
        sa.Column("research_limit", sa.Integer(), server_default="5", nullable=False),
        sa.Column("cap_tier", sa.String(16), nullable=True),
        sa.Column("strategy_key", sa.String(48), nullable=False),
        sa.Column("universe_limit", sa.Integer(), server_default="25", nullable=False),
        sa.Column("initial_capital", sa.Numeric(20, 4), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(16), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
            "queue_limit >= 1 AND queue_limit <= 50",
            name="ck_research_automation_policies_queue_limit",
        ),
        sa.CheckConstraint(
            "research_limit >= 1 AND research_limit <= queue_limit",
            name="ck_research_automation_policies_research_limit",
        ),
        sa.CheckConstraint(
            "universe_limit >= 5 AND universe_limit <= 30",
            name="ck_research_automation_policies_universe_limit",
        ),
        sa.CheckConstraint(
            "initial_capital > 0",
            name="ck_research_automation_policies_initial_capital",
        ),
        sa.CheckConstraint(
            "cap_tier IS NULL OR cap_tier IN "
            "('mega', 'large', 'mid', 'small', 'micro', 'penny')",
            name="ck_research_automation_policies_cap_tier",
        ),
        sa.CheckConstraint(
            "strategy_key IN ('dse_reversal_v1', 'us_breakout_v1')",
            name="ck_research_automation_policies_strategy",
        ),
        sa.CheckConstraint(
            "last_run_status IS NULL OR last_run_status IN "
            "('queued', 'running', 'succeeded', 'failed')",
            name="ck_research_automation_policies_last_status",
        ),
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_automation_policies_security_scope",
        ),
        sa.UniqueConstraint(
            "workspace_id", name="uq_research_automation_policies_workspace"
        ),
    )
    op.create_index(
        "ix_research_automation_policies_workspace_enabled",
        "research_automation_policies",
        ["workspace_id", "enabled"],
    )
    predicate = f"{_TENANT_SCOPE} AND ({_workspace_access('research_automation_policies')})"
    op.execute(sa.text("ALTER TABLE research_automation_policies ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE research_automation_policies FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY research_automation_policies_tenant_market_isolation "
            f"ON research_automation_policies USING ({predicate}) WITH CHECK ({predicate})"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP POLICY IF EXISTS research_automation_policies_tenant_market_isolation "
            "ON research_automation_policies"
        )
    )
    op.drop_table("research_automation_policies")
    op.drop_constraint("ck_research_runs_kind", "research_runs", type_="check")
    op.create_check_constraint(
        "ck_research_runs_kind",
        "research_runs",
        "run_kind IN ('dossier', 'deep_research', 'hypothesis', 'monitor', 'portfolio')",
    )
