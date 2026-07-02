"""company_logos: cached per-company logo bytes fetched from company websites

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
"""

import sqlalchemy as sa
from alembic import op

revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_logos",
        sa.Column("market", sa.String(length=8), primary_key=True),
        sa.Column("code", sa.String(length=16), primary_key=True),
        sa.Column("image", sa.LargeBinary(), nullable=True),
        sa.Column("content_type", sa.String(length=64), nullable=True),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ok"),
        sa.Column(
            "checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("company_logos")
