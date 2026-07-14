"""Add a public research-only symbol lifecycle state.

Revision ID: c91d7e2a4b6f
Revises: eba83b6dbacc
"""

from __future__ import annotations

from alembic import op

revision = "c91d7e2a4b6f"
down_revision = "eba83b6dbacc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_symbols_data_status", "symbols", type_="check")
    op.create_check_constraint(
        "ck_symbols_data_status",
        "symbols",
        "data_status IN ('reference_only', 'onboarding', 'ready', 'research_only', 'degraded')",
    )


def downgrade() -> None:
    op.execute("UPDATE symbols SET data_status = 'degraded' WHERE data_status = 'research_only'")
    op.drop_constraint("ck_symbols_data_status", "symbols", type_="check")
    op.create_check_constraint(
        "ck_symbols_data_status",
        "symbols",
        "data_status IN ('reference_only', 'onboarding', 'ready', 'degraded')",
    )
