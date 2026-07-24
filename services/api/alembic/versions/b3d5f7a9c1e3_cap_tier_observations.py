"""Append-only capitalization-tier history so archived sessions keep their real classification.

Revision ID: b3d5f7a9c1e3
Revises: a2b4c6d8e0f2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b3d5f7a9c1e3"
down_revision = "a2b4c6d8e0f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cap_tier_observations",
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("cap_tier", sa.String(16), nullable=True),
        sa.Column("market_cap_mn", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("market", "code", "as_of_date"),
    )


def downgrade() -> None:
    op.drop_table("cap_tier_observations")
