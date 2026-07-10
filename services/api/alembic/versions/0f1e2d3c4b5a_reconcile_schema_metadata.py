"""Reconcile timestamp constraints and remove a redundant portfolio index.

Revision ID: 0f1e2d3c4b5a
Revises: f0a1b2c3d4e5
"""

import sqlalchemy as sa
from alembic import op

revision = "0f1e2d3c4b5a"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None

_TIMESTAMP_COLUMNS = (
    ("alert_events", "created_at"),
    ("block_trades", "created_at"),
    ("follows", "created_at"),
    ("moderation_events", "created_at"),
    ("portfolio_holdings", "created_at"),
    ("portfolio_holdings", "updated_at"),
    ("portfolio_snapshots", "created_at"),
    ("price_alerts", "created_at"),
    ("quiz_answers", "created_at"),
    ("quiz_questions", "created_at"),
    ("refresh_sessions", "created_at"),
    ("trending_scores", "computed_at"),
)


def upgrade() -> None:
    for table_name, column_name in _TIMESTAMP_COLUMNS:
        op.execute(
            sa.text(
                f'UPDATE "{table_name}" SET "{column_name}" = now() '
                f'WHERE "{column_name}" IS NULL'
            )
        )
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )

    # The primary key already provides this exact (user_id, market, date) index.
    op.drop_index(
        "ix_portfolio_snapshots_user_market_date",
        table_name="portfolio_snapshots",
    )


def downgrade() -> None:
    op.create_index(
        "ix_portfolio_snapshots_user_market_date",
        "portfolio_snapshots",
        ["user_id", "market", "date"],
    )

    for table_name, column_name in reversed(_TIMESTAMP_COLUMNS):
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )
