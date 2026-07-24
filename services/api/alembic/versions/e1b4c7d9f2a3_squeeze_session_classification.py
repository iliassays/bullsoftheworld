"""Snapshot cap tier and traded value onto each squeeze state row

Revision ID: e1b4c7d9f2a3
Revises: d7f3a1c9e5b2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e1b4c7d9f2a3"
down_revision = "d7f3a1c9e5b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable and unbackfilled on purpose: rows archived before this migration genuinely do not
    # know their own session's classification, and inventing one would be the defect this fixes.
    op.add_column("squeeze_daily_states", sa.Column("cap_tier", sa.String(length=16)))
    op.add_column(
        "squeeze_daily_states", sa.Column("average_dollar_volume_mn", sa.Float())
    )


def downgrade() -> None:
    op.drop_column("squeeze_daily_states", "average_dollar_volume_mn")
    op.drop_column("squeeze_daily_states", "cap_tier")
