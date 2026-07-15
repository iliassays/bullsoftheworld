"""retain provider-reported quote turnover

Revision ID: c47e9a1b2d63
Revises: b42a0d8f3e95
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c47e9a1b2d63"
down_revision = "b42a0d8f3e95"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quote_snapshots", sa.Column("turnover_mn", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("quote_snapshots", "turnover_mn")
