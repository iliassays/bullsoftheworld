"""Reconcile FINRA volume precision for fractional odd-lot reports.

Revision ID: f2b6d8e0a3c5
Revises: e1a5c7d9f2b4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f2b6d8e0a3c5"
down_revision = "e1a5c7d9f2b4"
branch_labels = None
depends_on = None

_COLUMNS = ("short_volume", "short_exempt_volume", "total_volume")


def upgrade() -> None:
    for column in _COLUMNS:
        op.alter_column(
            "short_volume_daily",
            column,
            existing_type=sa.BigInteger(),
            type_=sa.Numeric(precision=24, scale=6),
            existing_nullable=False,
        )


def downgrade() -> None:
    for column in _COLUMNS:
        op.alter_column(
            "short_volume_daily",
            column,
            existing_type=sa.Numeric(precision=24, scale=6),
            type_=sa.BigInteger(),
            existing_nullable=False,
            postgresql_using=f'round("{column}")::bigint',
        )
