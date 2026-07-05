"""portfolio_snapshots — daily total value/cost per user, for the growth-over-time chart

No backfill: history starts the day this ships (see model docstring for why).

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
"""

import sqlalchemy as sa
from alembic import op

revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_snapshots",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("market", sa.String(length=8), primary_key=True),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("total_value", sa.Float(), nullable=True),
        sa.Column("total_cost", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_portfolio_snapshots_user_market_date",
        "portfolio_snapshots",
        ["user_id", "market", "date"],
    )


def downgrade() -> None:
    op.drop_index("ix_portfolio_snapshots_user_market_date", table_name="portfolio_snapshots")
    op.drop_table("portfolio_snapshots")
