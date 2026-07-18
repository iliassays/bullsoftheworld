"""Add durable settlement receivables to Atlas shadow snapshots.

Revision ID: d9e1f3a5b7c9
Revises: e0f2a4b6c8d0
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d9e1f3a5b7c9"
down_revision = "e0f2a4b6c8d0"
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


def _enable_rls(table: str) -> None:
    predicate = f"{_TENANT_SCOPE} AND ({_workspace_access(table)})"
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f'CREATE POLICY "{table}_tenant_market_isolation" ON "{table}" '
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
    )


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_research_shadow_portfolios_accounting_scope",
        "research_shadow_portfolios",
        ["id", "workspace_id", "organization_id", "tenant_id", "market"],
    )
    op.add_column(
        "research_shadow_snapshots",
        sa.Column(
            "pending_settlements",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_table(
        "research_accounting_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("session_number", sa.Integer(), nullable=False),
        sa.Column("event_key", sa.String(160), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("code", sa.String(32), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("sequence >= 0", name="ck_research_accounting_events_sequence"),
        sa.CheckConstraint(
            "session_number >= 0", name="ck_research_accounting_events_session_number"
        ),
        sa.CheckConstraint(
            "event_type IN ('opening_balance', 'methodology_boundary', "
            "'settlement_release', 'fill', 'valuation')",
            name="ck_research_accounting_events_type",
        ),
        sa.CheckConstraint("event_key <> ''", name="ck_research_accounting_events_key"),
        sa.CheckConstraint(
            "engine_version <> ''", name="ck_research_accounting_events_engine"
        ),
        sa.CheckConstraint(
            "payload_hash ~ '^[0-9a-f]{64}$'",
            name="ck_research_accounting_events_payload_hash",
        ),
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_accounting_events_security_scope",
        ),
        sa.UniqueConstraint(
            "portfolio_id", "sequence", name="uq_research_accounting_events_sequence"
        ),
        sa.UniqueConstraint(
            "portfolio_id", "event_key", name="uq_research_accounting_events_key"
        ),
    )
    op.create_index(
        "ix_research_accounting_events_workspace_recorded",
        "research_accounting_events",
        ["workspace_id", "recorded_at"],
    )
    op.create_index(
        "ix_research_accounting_events_portfolio_effective",
        "research_accounting_events",
        ["portfolio_id", "effective_date", "sequence"],
    )
    _enable_rls("research_accounting_events")
    op.execute(
        sa.text(
            "CREATE FUNCTION reject_research_accounting_event_mutation() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION "
            "'research_accounting_events are append-only'; END; $$"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER research_accounting_events_append_only "
            "BEFORE UPDATE OR DELETE ON research_accounting_events "
            "FOR EACH ROW EXECUTE FUNCTION reject_research_accounting_event_mutation()"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS research_accounting_events_append_only "
            "ON research_accounting_events"
        )
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS reject_research_accounting_event_mutation()"))
    op.execute(
        sa.text(
            "DROP POLICY IF EXISTS research_accounting_events_tenant_market_isolation "
            "ON research_accounting_events"
        )
    )
    op.drop_table("research_accounting_events")
    op.drop_column("research_shadow_snapshots", "pending_settlements")
    op.drop_constraint(
        "uq_research_shadow_portfolios_accounting_scope",
        "research_shadow_portfolios",
        type_="unique",
    )
