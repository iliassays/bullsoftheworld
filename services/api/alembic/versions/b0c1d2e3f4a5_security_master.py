"""security_master

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
"""

import sqlalchemy as sa
from alembic import op

revision = "b0c1d2e3f4a5"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_master",
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("raw_symbol", sa.String(length=32), nullable=False),
        sa.Column("security_name", sa.Text(), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=True),
        sa.Column("exchange_tier", sa.String(length=48), nullable=True),
        sa.Column("cqs_symbol", sa.String(length=32), nullable=True),
        sa.Column("nasdaq_symbol", sa.String(length=32), nullable=True),
        sa.Column("cik", sa.Integer(), nullable=True),
        sa.Column("instrument_type", sa.String(length=32), nullable=False),
        sa.Column("is_etf", sa.Boolean(), nullable=False),
        sa.Column("is_test_issue", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_product_eligible", sa.Boolean(), nullable=False),
        sa.Column("exclude_reason", sa.String(length=64), nullable=True),
        sa.Column("round_lot_size", sa.Integer(), nullable=True),
        sa.Column("financial_status", sa.String(length=8), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_file", sa.String(length=32), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("market", "symbol"),
    )
    op.create_index("ix_security_master_cik", "security_master", ["cik"], unique=False)
    op.create_index(
        "ix_security_master_market_eligible",
        "security_master",
        ["market", "is_product_eligible"],
        unique=False,
    )
    op.create_index(
        "ix_security_master_market_exchange",
        "security_master",
        ["market", "exchange"],
        unique=False,
    )
    op.create_index(
        "ix_security_master_market_instrument",
        "security_master",
        ["market", "instrument_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_security_master_market_instrument", table_name="security_master")
    op.drop_index("ix_security_master_market_exchange", table_name="security_master")
    op.drop_index("ix_security_master_market_eligible", table_name="security_master")
    op.drop_index("ix_security_master_cik", table_name="security_master")
    op.drop_table("security_master")
