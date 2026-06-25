"""company_profiles + shareholding_snapshots

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_profiles",
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("sector", sa.String(length=64), nullable=True),
        sa.Column("market_category", sa.String(length=4), nullable=True),
        sa.Column("instrument_type", sa.String(length=32), nullable=True),
        sa.Column("listing_year", sa.Integer(), nullable=True),
        sa.Column("face_value", sa.Float(), nullable=True),
        sa.Column("market_lot", sa.Integer(), nullable=True),
        sa.Column("authorized_capital_mn", sa.Float(), nullable=True),
        sa.Column("paid_up_capital_mn", sa.Float(), nullable=True),
        sa.Column("outstanding_shares", sa.Integer(), nullable=True),
        sa.Column("market_cap_mn", sa.Float(), nullable=True),
        sa.Column("free_float_mcap_mn", sa.Float(), nullable=True),
        sa.Column("year_end", sa.String(length=16), nullable=True),
        sa.Column("latest_dividend", sa.String(length=128), nullable=True),
        sa.Column("operational_status", sa.String(length=32), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("market", "code"),
    )
    op.create_table(
        "shareholding_snapshots",
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("sponsor_director", sa.Float(), nullable=True),
        sa.Column("govt", sa.Float(), nullable=True),
        sa.Column("institute", sa.Float(), nullable=True),
        sa.Column("foreign_pct", sa.Float(), nullable=True),  # 'foreign' is a SQL reserved word
        sa.Column("public", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("market", "code", "as_of_date"),
    )


def downgrade() -> None:
    op.drop_table("shareholding_snapshots")
    op.drop_table("company_profiles")
