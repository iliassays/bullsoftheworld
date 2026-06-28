"""image_url on posts (agent-generated card images, e.g. Evening Wrap)

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
"""

import sqlalchemy as sa
from alembic import op

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("image_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("posts", "image_url")
