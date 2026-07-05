"""users.portfolio_public — opt-in flag to show holdings on a public profile

Default false: private unless the user explicitly turns it on.

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
"""

import sqlalchemy as sa
from alembic import op

revision = "a4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("portfolio_public", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("users", "portfolio_public")
