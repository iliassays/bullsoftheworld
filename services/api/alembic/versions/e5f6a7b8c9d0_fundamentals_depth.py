"""debt/reserves on profile, financials+dividends+sector_pe tables, ownership+sector on analytics

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""

import sqlalchemy as sa
from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None

_PROFILE_COLS = ("short_term_loan_mn", "long_term_loan_mn", "reserve_surplus_mn", "oci_mn")
_ANALYTICS_COLS = (
    "pe_vs_sector",
    "eps_growth_yoy",
    "sponsor_pct",
    "institute_pct",
    "foreign_pct",
    "public_pct",
    "institute_delta",
    "foreign_delta",
)


def upgrade() -> None:
    for col in _PROFILE_COLS:
        op.add_column("company_profiles", sa.Column(col, sa.Float(), nullable=True))
    op.add_column("company_profiles", sa.Column("credit_rating_long", sa.String(48), nullable=True))
    op.add_column(
        "company_profiles", sa.Column("credit_rating_short", sa.String(48), nullable=True)
    )
    for col in _ANALYTICS_COLS:
        op.add_column("ticker_analytics", sa.Column(col, sa.Float(), nullable=True))

    op.create_table(
        "company_financials",
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("eps", sa.Float(), nullable=True),
        sa.Column("nav_per_share", sa.Float(), nullable=True),
        sa.Column("profit_mn", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("market", "code", "fiscal_year"),
    )
    op.create_table(
        "company_dividends",
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("cash_pct", sa.Float(), nullable=True),
        sa.Column("bonus_pct", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("market", "code", "year"),
    )
    op.create_table(
        "sector_pe",
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("sector", sa.String(length=64), nullable=False),
        sa.Column("median_pe", sa.Float(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("market", "sector"),
    )


def downgrade() -> None:
    op.drop_table("sector_pe")
    op.drop_table("company_dividends")
    op.drop_table("company_financials")
    for col in _ANALYTICS_COLS:
        op.drop_column("ticker_analytics", col)
    op.drop_column("company_profiles", "credit_rating_short")
    op.drop_column("company_profiles", "credit_rating_long")
    for col in _PROFILE_COLS:
        op.drop_column("company_profiles", col)
