"""trending_scores — daily 'Watch today' activity ranking

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trending_scores",
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("change_pct", sa.Float(), nullable=False),
        sa.Column("direction", sa.String(length=4), nullable=False),
        sa.Column("heating_up", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("market", "code"),
    )
    op.create_index("ix_trending_scores_as_of_date", "trending_scores", ["as_of_date"])
    op.create_index("ix_trending_scores_rank", "trending_scores", ["rank"])


def downgrade() -> None:
    op.drop_index("ix_trending_scores_rank", table_name="trending_scores")
    op.drop_index("ix_trending_scores_as_of_date", table_name="trending_scores")
    op.drop_table("trending_scores")
