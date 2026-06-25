"""company EPS/NAV/cash-div + derived valuation on ticker_analytics

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None

_PROFILE_COLS = ("cash_dividend_pct", "eps", "nav_per_share")
_ANALYTICS_COLS = ("market_cap_mn", "free_float_cap_mn", "pe_ratio", "pb_ratio", "dividend_yield")


def upgrade() -> None:
    for col in _PROFILE_COLS:
        op.add_column("company_profiles", sa.Column(col, sa.Float(), nullable=True))
    for col in _ANALYTICS_COLS:
        op.add_column("ticker_analytics", sa.Column(col, sa.Float(), nullable=True))


def downgrade() -> None:
    for col in _ANALYTICS_COLS:
        op.drop_column("ticker_analytics", col)
    for col in _PROFILE_COLS:
        op.drop_column("company_profiles", col)
