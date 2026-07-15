"""ticker_analytics.cap_tier: denormalized canonical size tier for SQL filtering

Nullable — NULL means "unclassified" (no reliable market cap), which the UI must show as its own
bucket rather than guessing a tier. Populated by refresh_analytics on its next run; no data
backfill needed here.

Revision ID: caa7b5fd5b0b
Revises: c91d7e2a4b6f
"""

import sqlalchemy as sa
from alembic import op

revision = "caa7b5fd5b0b"
down_revision = "c91d7e2a4b6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ticker_analytics", sa.Column("cap_tier", sa.String(length=16), nullable=True))
    # Screener/browse filter shape: WHERE market = ? AND cap_tier = ?
    op.create_index(
        "ix_ticker_analytics_market_cap_tier", "ticker_analytics", ["market", "cap_tier"]
    )


def downgrade() -> None:
    op.drop_index("ix_ticker_analytics_market_cap_tier", table_name="ticker_analytics")
    op.drop_column("ticker_analytics", "cap_tier")
