"""body_i18n on posts (bilingual agent desk-notes: {"en": ..., "bn": ...})

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
"""

import sqlalchemy as sa
from alembic import op

revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("body_i18n", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("posts", "body_i18n")
