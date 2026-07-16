"""Add immutable daily Hedge scan publications.

Revision ID: a7c9e1f3b5d7
Revises: f9c2d3e4a5b6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a7c9e1f3b5d7"
down_revision = "f9c2d3e4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hedge_daily_scan_snapshots",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("strategy", sa.String(32), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_hedge_daily_scan_content_hash",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "market",
            "strategy",
            "as_of_date",
        ),
    )
    predicate = "tenant_id = current_setting('app.tenant_id', true)"
    op.execute(sa.text("ALTER TABLE hedge_daily_scan_snapshots ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE hedge_daily_scan_snapshots FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY hedge_daily_scan_snapshots_tenant_isolation "
            "ON hedge_daily_scan_snapshots "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION prevent_hedge_daily_scan_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'hedge daily scan publications are append-only';
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER hedge_daily_scan_append_only
            BEFORE UPDATE OR DELETE ON hedge_daily_scan_snapshots
            FOR EACH ROW EXECUTE FUNCTION prevent_hedge_daily_scan_mutation()
            """
        )
    )


def downgrade() -> None:
    op.drop_table("hedge_daily_scan_snapshots")
    op.execute(sa.text("DROP FUNCTION prevent_hedge_daily_scan_mutation()"))
