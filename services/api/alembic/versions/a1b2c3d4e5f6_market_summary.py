"""market_summary

Revision ID: a1b2c3d4e5f6
Revises: 981c6f2c6b0e
"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "981c6f2c6b0e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_summary",
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("dsex", sa.Float(), nullable=True),
        sa.Column("dsex_change", sa.Float(), nullable=True),
        sa.Column("ds30", sa.Float(), nullable=True),
        sa.Column("ds30_change", sa.Float(), nullable=True),
        sa.Column("total_trade", sa.Integer(), nullable=True),
        sa.Column("total_value_mn", sa.Float(), nullable=True),
        sa.Column("total_volume", sa.Integer(), nullable=True),
        sa.Column("total_market_cap_mn", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("market", "date"),
    )


def downgrade() -> None:
    op.drop_table("market_summary")
