"""Add complete snapshot metadata to the daily shortlist archive.

Revision ID: c6f8a0b2d4e7
Revises: b5e7d2f4a9c1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c6f8a0b2d4e7"
down_revision = "b5e7d2f4a9c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "daily_shortlist_states",
        sa.Column("excluded_illiquid", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "daily_shortlist_states",
        sa.Column("excluded_short_history", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "daily_shortlist_states",
        sa.Column("slate_size", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "daily_shortlist_states",
        sa.Column(
            "notes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "daily_shortlist_states",
        sa.Column(
            "base_rates",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_check_constraint(
        "ck_daily_shortlist_states_counts",
        "daily_shortlist_states",
        "eligible_names >= 0 AND excluded_illiquid >= 0 AND excluded_short_history >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_daily_shortlist_states_counts",
        "daily_shortlist_states",
        type_="check",
    )
    op.drop_column("daily_shortlist_states", "base_rates")
    op.drop_column("daily_shortlist_states", "notes")
    op.drop_column("daily_shortlist_states", "slate_size")
    op.drop_column("daily_shortlist_states", "excluded_short_history")
    op.drop_column("daily_shortlist_states", "excluded_illiquid")
