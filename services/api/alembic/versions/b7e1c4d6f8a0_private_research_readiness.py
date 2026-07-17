"""Separate private research readiness from public symbol publication.

Revision ID: b7e1c4d6f8a0
Revises: a4c6e8f0b2d1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b7e1c4d6f8a0"
down_revision = "a4c6e8f0b2d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "symbols",
        sa.Column(
            "research_status",
            sa.String(length=20),
            nullable=False,
            server_default="ready",
        ),
    )
    op.add_column(
        "symbols",
        sa.Column(
            "research_status_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_check_constraint(
        "ck_symbols_research_status",
        "symbols",
        "research_status IN "
        "('reference_only', 'onboarding', 'ready', 'partial', 'degraded', 'unavailable')",
    )
    op.create_index(
        "ix_symbols_research_status",
        "symbols",
        ["research_status"],
        unique=False,
    )
    op.execute(
        "UPDATE symbols SET research_status = CASE "
        "WHEN data_status IN ('ready', 'research_only') THEN 'ready' "
        "WHEN data_status = 'onboarding' THEN 'onboarding' "
        "WHEN data_status = 'degraded' THEN 'degraded' "
        "ELSE 'reference_only' END"
    )
    op.execute(
        "UPDATE symbols AS s SET research_status = 'ready', "
        "research_status_updated_at = latest.evaluated_at "
        "FROM ("
        "SELECT DISTINCT ON (r.market, r.code) r.market, r.code, r.evaluated_at "
        "FROM universe_onboarding_results AS r "
        "JOIN universe_onboarding_runs AS u ON u.id = r.run_id "
        "WHERE u.status = 'completed' AND r.required_gates_passed IS TRUE "
        "ORDER BY r.market, r.code, r.evaluated_at DESC"
        ") AS latest "
        "WHERE s.market = latest.market AND s.code = latest.code"
    )


def downgrade() -> None:
    op.drop_index("ix_symbols_research_status", table_name="symbols")
    op.drop_constraint("ck_symbols_research_status", "symbols", type_="check")
    op.drop_column("symbols", "research_status_updated_at")
    op.drop_column("symbols", "research_status")
