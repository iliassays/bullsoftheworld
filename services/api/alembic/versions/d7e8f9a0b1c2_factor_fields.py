"""momentum, volatility, roe on ticker_analytics

Revision ID: d7e8f9a0b1c2
Revises: c5bb55bcd935
"""

import sqlalchemy as sa
from alembic import op

revision = "d7e8f9a0b1c2"
down_revision = "c5bb55bcd935"
branch_labels = None
depends_on = None

_ANALYTICS_COLS = ("mom_12_1", "volatility", "roe")


def upgrade() -> None:
    for col in _ANALYTICS_COLS:
        op.add_column("ticker_analytics", sa.Column(col, sa.Float(), nullable=True))


def downgrade() -> None:
    for col in _ANALYTICS_COLS:
        op.drop_column("ticker_analytics", col)
