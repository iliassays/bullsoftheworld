"""short_volume_daily: FINRA Reg SHO daily consolidated short-sale volume per symbol

Revision ID: eba83b6dbacc
Revises: 8b9c0d1e2f3a
"""

import sqlalchemy as sa
from alembic import op

revision = "eba83b6dbacc"
down_revision = "8b9c0d1e2f3a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "short_volume_daily",
        sa.Column("market", sa.String(length=8), primary_key=True),
        sa.Column("code", sa.String(length=16), primary_key=True),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("short_volume", sa.Numeric(precision=24, scale=6), nullable=False),
        sa.Column("short_exempt_volume", sa.Numeric(precision=24, scale=6), nullable=False),
        sa.Column("total_volume", sa.Numeric(precision=24, scale=6), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="finra_cnms"),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_short_volume_daily_market_date", "short_volume_daily", ["market", "date"])


def downgrade() -> None:
    op.drop_index("ix_short_volume_daily_market_date", table_name="short_volume_daily")
    op.drop_table("short_volume_daily")
