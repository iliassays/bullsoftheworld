"""block_trades — per-scrip block-market deals (internal dataset, admin-only surface)

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
"""

import sqlalchemy as sa
from alembic import op

revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "block_trades",
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("value_mn", sa.Float(), nullable=False),
        sa.Column("trades", sa.Integer(), nullable=False),
        sa.Column("max_price", sa.Float(), nullable=True),
        sa.Column("min_price", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("market", "code", "trade_date"),
    )
    op.create_index("ix_block_trades_trade_date", "block_trades", ["trade_date"])


def downgrade() -> None:
    op.drop_index("ix_block_trades_trade_date", table_name="block_trades")
    op.drop_table("block_trades")
