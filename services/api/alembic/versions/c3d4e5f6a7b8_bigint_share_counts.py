"""widen share/volume counts to BigInteger (int32 overflow)

Large-caps exceed int32: e.g. ROBI has 5.2B outstanding shares, and market-wide daily volume
already nears 2.1B. Widen both count columns to int8.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("company_profiles", "outstanding_shares", type_=sa.BigInteger())
    op.alter_column("market_summary", "total_volume", type_=sa.BigInteger())


def downgrade() -> None:
    op.alter_column("market_summary", "total_volume", type_=sa.Integer())
    op.alter_column("company_profiles", "outstanding_shares", type_=sa.Integer())
