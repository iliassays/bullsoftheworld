"""tenant-scope social metrics and page views

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
"""

import sqlalchemy as sa
from alembic import op

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "page_view_events",
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
    )
    op.execute(
        "UPDATE page_view_events SET tenant_id = "
        "CASE WHEN market = 'US' THEN 'bullsofwallst' ELSE 'bullsofdhaka' END"
    )
    op.alter_column("page_view_events", "tenant_id", nullable=False)
    op.drop_index("ix_page_view_market_code_created", table_name="page_view_events")
    op.create_index(
        "ix_page_view_tenant_market_code_created",
        "page_view_events",
        ["tenant_id", "market", "code", "created_at"],
    )
    op.create_index("ix_page_view_events_tenant_id", "page_view_events", ["tenant_id"])

    op.add_column(
        "ticker_buzz_daily",
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
    )
    op.execute(
        "UPDATE ticker_buzz_daily SET tenant_id = "
        "CASE WHEN market = 'US' THEN 'bullsofwallst' ELSE 'bullsofdhaka' END"
    )
    op.alter_column("ticker_buzz_daily", "tenant_id", nullable=False)
    op.drop_constraint("ticker_buzz_daily_pkey", "ticker_buzz_daily", type_="primary")
    op.create_primary_key(
        "ticker_buzz_daily_pkey",
        "ticker_buzz_daily",
        ["tenant_id", "market", "code", "date"],
    )


def downgrade() -> None:
    op.drop_constraint("ticker_buzz_daily_pkey", "ticker_buzz_daily", type_="primary")
    op.create_primary_key(
        "ticker_buzz_daily_pkey", "ticker_buzz_daily", ["market", "code", "date"]
    )
    op.drop_column("ticker_buzz_daily", "tenant_id")

    op.drop_index("ix_page_view_events_tenant_id", table_name="page_view_events")
    op.drop_index(
        "ix_page_view_tenant_market_code_created", table_name="page_view_events"
    )
    op.create_index(
        "ix_page_view_market_code_created",
        "page_view_events",
        ["market", "code", "created_at"],
    )
    op.drop_column("page_view_events", "tenant_id")
