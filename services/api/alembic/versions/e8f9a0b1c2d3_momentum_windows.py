"""3m and 6m momentum windows on ticker_analytics

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
"""

import sqlalchemy as sa
from alembic import op

revision = "e8f9a0b1c2d3"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None

_ANALYTICS_COLS = ("mom_3_1", "mom_6_1")


def upgrade() -> None:
    for col in _ANALYTICS_COLS:
        op.add_column("ticker_analytics", sa.Column(col, sa.Float(), nullable=True))


def downgrade() -> None:
    for col in _ANALYTICS_COLS:
        op.drop_column("ticker_analytics", col)
