"""retain daily-bar adjustment and provider provenance

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
"""

import sqlalchemy as sa
from alembic import op

revision = "a5b6c7d8e9f0"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("daily_bars", sa.Column("adjusted_close", sa.Float(), nullable=True))
    op.add_column(
        "daily_bars",
        sa.Column("source", sa.String(length=32), server_default="unknown", nullable=False),
    )
    op.execute("UPDATE daily_bars SET source = 'dse_archive' WHERE market = 'DSE'")
    op.execute("UPDATE daily_bars SET source = 'yahoo_chart' WHERE market = 'US'")


def downgrade() -> None:
    op.drop_column("daily_bars", "source")
    op.drop_column("daily_bars", "adjusted_close")
