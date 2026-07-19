"""Retain DSE no-trade observations and label official-close sampled prices.

Revision ID: f1e3a5c7d9b0
Revises: e0f2a4b6c8d0
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f1e3a5c7d9b0"
down_revision = "e0f2a4b6c8d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_intraday_quote_observations_ltp",
        "intraday_quote_observations",
        type_="check",
    )
    op.drop_constraint(
        "ck_intraday_quote_observations_range",
        "intraday_quote_observations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_intraday_quote_observations_ltp",
        "intraday_quote_observations",
        "ltp >= 0",
    )
    op.create_check_constraint(
        "ck_intraday_quote_observations_range",
        "intraday_quote_observations",
        "high >= 0 AND low >= 0 AND close >= 0",
    )
    op.add_column(
        "intraday_quote_observations",
        sa.Column("price_basis", sa.String(length=24), server_default="last_trade", nullable=False),
    )
    op.create_check_constraint(
        "ck_intraday_quote_observations_price_basis",
        "intraday_quote_observations",
        "price_basis IN ('last_trade', 'official_close', 'unavailable')",
    )
    op.add_column(
        "intraday_bars",
        sa.Column("price_basis", sa.String(length=24), server_default="last_trade", nullable=False),
    )
    op.create_check_constraint(
        "ck_intraday_bars_price_basis",
        "intraday_bars",
        "price_basis IN ('last_trade', 'official_close')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_intraday_bars_price_basis", "intraday_bars", type_="check")
    op.drop_column("intraday_bars", "price_basis")
    op.drop_constraint(
        "ck_intraday_quote_observations_price_basis",
        "intraday_quote_observations",
        type_="check",
    )
    op.drop_column("intraday_quote_observations", "price_basis")
    op.drop_constraint(
        "ck_intraday_quote_observations_range",
        "intraday_quote_observations",
        type_="check",
    )
    op.drop_constraint(
        "ck_intraday_quote_observations_ltp",
        "intraday_quote_observations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_intraday_quote_observations_range",
        "intraday_quote_observations",
        "high > 0 AND low > 0",
    )
    op.create_check_constraint(
        "ck_intraday_quote_observations_ltp",
        "intraday_quote_observations",
        "ltp > 0",
    )
