"""obv_slope on ticker_analytics (On-Balance Volume trend, volume-leads-price)

Revision ID: a0b1c2d3e4f5
Revises: f9a0b1c2d3e4
"""

import sqlalchemy as sa
from alembic import op

revision = "a0b1c2d3e4f5"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ticker_analytics", sa.Column("obv_slope", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("ticker_analytics", "obv_slope")
