"""Reconcile the append-only research audit ledger.

Revision ID: a31f9c7e2d84
Revises: f2b6d8e0a3c5

An early development database applied the research foundation before its audit-ledger DDL was
finalized. Never edit that applied revision again: this forward-only migration safely converges
both the drifted database and databases where the table already exists.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a31f9c7e2d84"
down_revision = "f2b6d8e0a3c5"
branch_labels = None
depends_on = None

_USER_ID = "NULLIF(current_setting('app.research_user_id', true), '')::integer"
_POLICY = (
    "tenant_id = current_setting('app.research_tenant_id', true) "
    "AND market = current_setting('app.research_market', true) "
    "AND EXISTS (SELECT 1 FROM research_organization_memberships rom "
    "WHERE rom.organization_id = research_audit_events.organization_id "
    "AND rom.tenant_id = research_audit_events.tenant_id "
    "AND rom.market = research_audit_events.market "
    f"AND rom.user_id = {_USER_ID} AND rom.status = 'active' "
    "AND (rom.role IN ('owner', 'admin') OR EXISTS ("
    "SELECT 1 FROM research_workspace_memberships rwm "
    "WHERE rwm.workspace_id = research_audit_events.workspace_id "
    "AND rwm.organization_id = research_audit_events.organization_id "
    "AND rwm.tenant_id = research_audit_events.tenant_id "
    "AND rwm.market = research_audit_events.market "
    f"AND rwm.user_id = {_USER_ID} AND rwm.status = 'active')))"
)


def _create_table() -> None:
    op.create_table(
        "research_audit_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(48), nullable=False),
        sa.Column("resource_id", sa.String(160), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("event_type <> ''", name="ck_research_audit_events_event_type"),
        sa.CheckConstraint("resource_type <> ''", name="ck_research_audit_events_resource_type"),
        sa.CheckConstraint("resource_id <> ''", name="ck_research_audit_events_resource_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "organization_id", "tenant_id", "market"],
            [
                "research_workspaces.id",
                "research_workspaces.organization_id",
                "research_workspaces.tenant_id",
                "research_workspaces.market",
            ],
            name="fk_research_audit_events_workspace_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_user_id", "tenant_id", "market"],
            [
                "research_organization_memberships.organization_id",
                "research_organization_memberships.user_id",
                "research_organization_memberships.tenant_id",
                "research_organization_memberships.market",
            ],
            name="fk_research_audit_events_actor_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_audit_events_workspace_occurred",
        "research_audit_events",
        ["workspace_id", "occurred_at"],
    )
    op.create_index(
        "ix_research_audit_events_org_actor_occurred",
        "research_audit_events",
        ["organization_id", "actor_user_id", "occurred_at"],
    )


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("research_audit_events"):
        _create_table()

    op.execute(
        sa.text(
            "CREATE OR REPLACE FUNCTION reject_research_audit_mutation() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN "
            "IF current_user = pg_get_userbyid((SELECT relowner FROM pg_class "
            "WHERE oid = TG_RELID)) THEN RETURN OLD; END IF; "
            "RAISE EXCEPTION 'research audit events are append-only' USING ERRCODE = '55000'; "
            "END; $$"
        )
    )
    op.execute(sa.text("DROP TRIGGER IF EXISTS research_audit_events_append_only ON research_audit_events"))
    op.execute(
        sa.text(
            "CREATE TRIGGER research_audit_events_append_only "
            "BEFORE UPDATE OR DELETE ON research_audit_events "
            "FOR EACH ROW EXECUTE FUNCTION reject_research_audit_mutation()"
        )
    )
    op.execute(sa.text("ALTER TABLE research_audit_events ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE research_audit_events FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "DROP POLICY IF EXISTS research_audit_events_tenant_market_isolation "
            "ON research_audit_events"
        )
    )
    op.execute(
        sa.text(
            "CREATE POLICY research_audit_events_tenant_market_isolation "
            f"ON research_audit_events USING ({_POLICY}) WITH CHECK ({_POLICY})"
        )
    )


def downgrade() -> None:
    # Reconciliation migrations are intentionally non-destructive: the table may predate this
    # revision and can contain an immutable security audit trail.
    pass
