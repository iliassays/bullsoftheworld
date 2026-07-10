"""Allow full exchange-provided English symbol names.

Revision ID: 1a2b3c4d5e6f
Revises: 0f1e2d3c4b5a
"""

import sqlalchemy as sa
from alembic import op

revision = "1a2b3c4d5e6f"
down_revision = "0f1e2d3c4b5a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "symbols",
        "name_en",
        existing_type=sa.String(length=160),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    # PostgreSQL refuses this downgrade if any official name is longer than 160 characters,
    # which is preferable to silently truncating identity data.
    op.alter_column(
        "symbols",
        "name_en",
        existing_type=sa.Text(),
        type_=sa.String(length=160),
        existing_nullable=False,
    )
