"""Catalyst events: typed, tenant-shared official event calendar for Atlas.

Revision ID: b8d0e2f4a6c8
Revises: a7c9e1f3b5d7
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b8d0e2f4a6c8"
down_revision = "a7c9e1f3b5d7"
branch_labels = None
depends_on = None

_TABLE = "research_catalyst_events"
_TENANT_SCOPE = (
    "tenant_id = current_setting('app.research_tenant_id', true) "
    "AND market = current_setting('app.research_market', true)"
)


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(32), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("timing_kind", sa.String(12), nullable=False),
        sa.Column("confirmed_date", sa.Date(), nullable=True),
        sa.Column("window_start", sa.Date(), nullable=True),
        sa.Column("window_end", sa.Date(), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="scheduled"),
        sa.Column("confidence", sa.String(24), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.String(128), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_evidence", sa.Text(), nullable=True),
        sa.Column("outcome", postgresql.JSONB(), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("dedupe_key", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "event_type IN ('record_date', 'agm', 'egm', 'board_meeting', "
            "'spot_window', 'periodic_report_window')",
            name="ck_research_catalyst_event_type",
        ),
        sa.CheckConstraint(
            "timing_kind IN ('confirmed', 'window')",
            name="ck_research_catalyst_timing_kind",
        ),
        sa.CheckConstraint(
            "confidence IN ('official_confirmed', 'official_derived', 'inferred_cadence')",
            name="ck_research_catalyst_confidence",
        ),
        sa.CheckConstraint(
            "status IN ('scheduled', 'occurred', 'cancelled')",
            name="ck_research_catalyst_status",
        ),
        sa.CheckConstraint(
            "(timing_kind = 'confirmed' AND confirmed_date IS NOT NULL "
            "AND window_start IS NULL AND window_end IS NULL) OR "
            "(timing_kind = 'window' AND confirmed_date IS NULL "
            "AND window_start IS NOT NULL AND window_end IS NOT NULL "
            "AND window_start <= window_end)",
            name="ck_research_catalyst_timing_shape",
        ),
        sa.CheckConstraint(
            "dedupe_key ~ '^[0-9a-f]{64}$'",
            name="ck_research_catalyst_dedupe_key",
        ),
    )
    op.create_index(
        "ix_research_catalyst_events_tenant_confirmed",
        _TABLE,
        ["tenant_id", "market", "confirmed_date"],
    )
    op.create_index(
        "ix_research_catalyst_events_tenant_window",
        _TABLE,
        ["tenant_id", "market", "window_start"],
    )
    op.create_index("ix_research_catalyst_events_security", _TABLE, ["market", "code"])

    op.execute(sa.text(f'ALTER TABLE "{_TABLE}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{_TABLE}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f'CREATE POLICY "{_TABLE}_tenant_scope" ON "{_TABLE}" '
            f"USING ({_TENANT_SCOPE}) WITH CHECK ({_TENANT_SCOPE})"
        )
    )


def downgrade() -> None:
    op.execute(sa.text(f'DROP POLICY IF EXISTS "{_TABLE}_tenant_scope" ON "{_TABLE}"'))
    op.drop_table(_TABLE)
