"""agent_portfolios / agent_trades / agent_lots — simulated model portfolios run by strategy rules

The agent users themselves are plain `users` rows; holdings reuse `portfolio_holdings`. These
tables add the broker-account simulation: settled cash, executions with T+2/T+3 settlement dates,
and FIFO share lots that only become sellable at settlement.

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
"""

import sqlalchemy as sa
from alembic import op

revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_portfolios",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("strategy", sa.String(length=24), nullable=False),
        sa.Column("initial_capital", sa.Float(), nullable=False),
        sa.Column("cash_settled", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "agent_trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=4), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("fee", sa.Float(), nullable=False),
        sa.Column("net_cash", sa.Float(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("settles_on", sa.Date(), nullable=False),
        sa.Column("settled", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("quote_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_trades_user_id", "agent_trades", ["user_id"], unique=False)
    op.create_table(
        "agent_lots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("quantity_left", sa.Integer(), nullable=False),
        sa.Column("buy_price", sa.Float(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("sellable_from", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_lots_user_id", "agent_lots", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_lots_user_id", table_name="agent_lots")
    op.drop_table("agent_lots")
    op.drop_index("ix_agent_trades_user_id", table_name="agent_trades")
    op.drop_table("agent_trades")
    op.drop_table("agent_portfolios")
