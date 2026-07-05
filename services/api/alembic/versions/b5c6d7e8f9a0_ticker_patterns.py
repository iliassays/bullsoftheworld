"""ticker_patterns — daily chart-pattern detection (Finviz-style: triangles, channels, doubles)

One row per code, replaced nightly by the same job that fills ticker_analytics. No row means
"nothing detected" — never a fake/empty placeholder.

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b5c6d7e8f9a0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticker_patterns",
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("pattern_type", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("breakout_date", sa.Date(), nullable=True),
        sa.Column("strength_score", sa.Float(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("market", "code"),
    )
    op.create_index(
        "ix_ticker_patterns_as_of_date", "ticker_patterns", ["as_of_date"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_ticker_patterns_as_of_date", table_name="ticker_patterns")
    op.drop_table("ticker_patterns")
