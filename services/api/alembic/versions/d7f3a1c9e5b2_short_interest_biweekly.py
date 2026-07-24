"""FINRA bi-monthly consolidated short interest

Revision ID: d7f3a1c9e5b2
Revises: c4e6a8b0d2f4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d7f3a1c9e5b2"
down_revision = "c4e6a8b0d2f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "short_interest_biweekly",
        sa.Column("market", sa.String(length=8), primary_key=True),
        sa.Column("code", sa.String(length=16), primary_key=True),
        sa.Column("settlement_date", sa.Date(), primary_key=True),
        # Research must gate on known_at, never settlement_date — see the model docstring.
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "first_observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("shares_short", sa.Numeric(24, 4), nullable=False),
        sa.Column("previous_shares_short", sa.Numeric(24, 4)),
        sa.Column("average_daily_volume", sa.Numeric(24, 4)),
        sa.Column("days_to_cover", sa.Numeric(14, 4)),
        sa.Column("change_pct", sa.Numeric(14, 4)),
        sa.Column("market_class", sa.String(length=16)),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="finra_consolidated",
        ),
        sa.CheckConstraint("shares_short >= 0", name="ck_short_interest_shares_non_negative"),
        sa.CheckConstraint(
            "known_at >= settlement_date::timestamptz",
            name="ck_short_interest_known_after_settlement",
        ),
    )
    op.create_index(
        "ix_short_interest_market_known",
        "short_interest_biweekly",
        ["market", "known_at"],
    )
    op.create_index(
        "ix_short_interest_market_code_known",
        "short_interest_biweekly",
        ["market", "code", "known_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_short_interest_market_code_known", table_name="short_interest_biweekly")
    op.drop_index("ix_short_interest_market_known", table_name="short_interest_biweekly")
    op.drop_table("short_interest_biweekly")
