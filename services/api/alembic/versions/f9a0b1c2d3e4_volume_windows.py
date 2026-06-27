"""5d and 1m relative-volume windows on ticker_analytics

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
"""

import sqlalchemy as sa
from alembic import op

revision = "f9a0b1c2d3e4"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None

_ANALYTICS_COLS = ("rel_volume_5d", "rel_volume_1m")


def upgrade() -> None:
    for col in _ANALYTICS_COLS:
        op.add_column("ticker_analytics", sa.Column(col, sa.Float(), nullable=True))


def downgrade() -> None:
    for col in _ANALYTICS_COLS:
        op.drop_column("ticker_analytics", col)
