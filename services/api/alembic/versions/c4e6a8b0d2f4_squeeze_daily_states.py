"""Append-only squeeze-taxonomy daily state archive.

Revision ID: c4e6a8b0d2f4
Revises: b3d5f7a9c1e3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "c4e6a8b0d2f4"
down_revision = "b3d5f7a9c1e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "squeeze_daily_states",
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("family", sa.String(40), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("previous_state", sa.String(16), nullable=True),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("setup_price", sa.Float(), nullable=True),
        sa.Column("trigger_price", sa.Float(), nullable=True),
        sa.Column("invalidation_price", sa.Float(), nullable=True),
        sa.Column("risk_per_share", sa.Float(), nullable=True),
        sa.Column("planning_objective_price", sa.Float(), nullable=True),
        sa.Column("first_discovered_on", sa.Date(), nullable=False),
        sa.Column("evidence", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("methodology_version", sa.String(48), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("market", "code", "family", "as_of_date"),
    )
    op.create_index(
        "ix_squeeze_daily_states_market_date", "squeeze_daily_states", ["market", "as_of_date"]
    )
    op.create_index(
        "ix_squeeze_daily_states_market_code_family",
        "squeeze_daily_states",
        ["market", "code", "family"],
    )


def downgrade() -> None:
    op.drop_table("squeeze_daily_states")
