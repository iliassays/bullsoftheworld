"""widen symbol volume columns to BigInteger

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
"""

import sqlalchemy as sa
from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "b0c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("daily_bars", "volume", type_=sa.BigInteger())
    op.alter_column("quote_snapshots", "volume", type_=sa.BigInteger())


def downgrade() -> None:
    op.alter_column("quote_snapshots", "volume", type_=sa.Integer())
    op.alter_column("daily_bars", "volume", type_=sa.Integer())
