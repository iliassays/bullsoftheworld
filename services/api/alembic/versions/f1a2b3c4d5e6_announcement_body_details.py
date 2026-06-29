"""announcement body + decoded details (trader-friendly news)

Revision ID: f1a2b3c4d5e6
Revises: e4f5a6b7c8d9
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f1a2b3c4d5e6"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("announcements", sa.Column("body", sa.Text(), nullable=True))
    op.add_column(
        "announcements",
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("announcements", "details")
    op.drop_column("announcements", "body")
