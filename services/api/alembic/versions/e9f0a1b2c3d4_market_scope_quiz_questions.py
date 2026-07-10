"""market-scope daily quiz question banks

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
"""

import sqlalchemy as sa
from alembic import op

revision = "e9f0a1b2c3d4"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quiz_questions",
        sa.Column("market", sa.String(length=8), server_default="DSE", nullable=False),
    )
    op.create_index("ix_quiz_questions_market", "quiz_questions", ["market"])


def downgrade() -> None:
    op.drop_index("ix_quiz_questions_market", table_name="quiz_questions")
    op.drop_column("quiz_questions", "market")
