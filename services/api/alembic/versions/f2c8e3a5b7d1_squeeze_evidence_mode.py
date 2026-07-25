"""Distinguish forward-collected squeeze states from reconstructed ones

Revision ID: f2c8e3a5b7d1
Revises: e1b4c7d9f2a3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f2c8e3a5b7d1"
down_revision = "e1b4c7d9f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing rows were written by the nightly scan on their own session, so they are genuinely
    # forward evidence; the default is correct for them.
    op.add_column(
        "squeeze_daily_states",
        sa.Column(
            "evidence_mode",
            sa.String(length=16),
            nullable=False,
            server_default="forward",
        ),
    )
    op.create_check_constraint(
        "ck_squeeze_daily_states_evidence_mode",
        "squeeze_daily_states",
        "evidence_mode IN ('forward', 'reconstructed')",
    )
    op.create_index(
        "ix_squeeze_daily_states_market_mode_date",
        "squeeze_daily_states",
        ["market", "evidence_mode", "as_of_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_squeeze_daily_states_market_mode_date", table_name="squeeze_daily_states"
    )
    op.drop_constraint(
        "ck_squeeze_daily_states_evidence_mode", "squeeze_daily_states", type_="check"
    )
    op.drop_column("squeeze_daily_states", "evidence_mode")
