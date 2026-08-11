"""Persist versioned Atlas condition evidence and opt-in alerts.

Revision ID: a6c8e0f2b4d6
Revises: e5a7c9b1d3f5
Create Date: 2026-08-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a6c8e0f2b4d6"
down_revision = "e5a7c9b1d3f5"
branch_labels = None
depends_on = None

_TRANSITIONS = "research_condition_transitions"
_CALIBRATIONS = "research_condition_calibrations"
_SUBSCRIPTIONS = "atlas_condition_subscriptions"


def upgrade() -> None:
    op.create_table(
        _TRANSITIONS,
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("condition_key", sa.String(48), nullable=False),
        sa.Column("condition_version", sa.String(24), nullable=False),
        sa.Column("methodology_version", sa.String(48), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("previous_state", sa.String(16), nullable=True),
        sa.Column("reference_close", sa.Float(), nullable=False),
        sa.Column(
            "checks",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "outcomes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("evidence_mode", sa.String(16), server_default="forward", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "state IN ('observed', 'not_observed', 'unavailable')",
            name="ck_research_condition_transitions_state",
        ),
        sa.CheckConstraint(
            "previous_state IS NULL OR previous_state IN "
            "('observed', 'not_observed', 'unavailable')",
            name="ck_research_condition_transitions_previous_state",
        ),
        sa.CheckConstraint(
            "evidence_mode IN ('forward', 'reconstructed')",
            name="ck_research_condition_transitions_evidence_mode",
        ),
        sa.CheckConstraint(
            "reference_close > 0", name="ck_research_condition_transitions_reference_close"
        ),
        sa.ForeignKeyConstraint(
            ["market", "code"],
            ["symbols.market", "symbols.code"],
            name="fk_research_condition_transitions_symbol",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "market",
            "code",
            "condition_key",
            "condition_version",
            "methodology_version",
            "as_of_date",
        ),
    )
    op.create_index(
        "ix_research_condition_transitions_market_condition_date",
        _TRANSITIONS,
        ["market", "condition_key", "as_of_date"],
    )
    op.create_index(
        "ix_research_condition_transitions_market_code_condition",
        _TRANSITIONS,
        ["market", "code", "condition_key", "as_of_date"],
    )

    op.create_table(
        _CALIBRATIONS,
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("condition_key", sa.String(48), nullable=False),
        sa.Column("condition_version", sa.String(24), nullable=False),
        sa.Column("methodology_version", sa.String(48), nullable=False),
        sa.Column("evidence_mode", sa.String(16), nullable=False),
        sa.Column("horizon_sessions", sa.Integer(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("history_start_date", sa.Date(), nullable=True),
        sa.Column("observations", sa.Integer(), nullable=False),
        sa.Column("matured", sa.Integer(), nullable=False),
        sa.Column("pending", sa.Integer(), nullable=False),
        sa.Column("average_return_pct", sa.Float(), nullable=True),
        sa.Column("median_return_pct", sa.Float(), nullable=True),
        sa.Column("positive_rate_pct", sa.Float(), nullable=True),
        sa.Column("average_benchmark_return_pct", sa.Float(), nullable=True),
        sa.Column("median_excess_return_pct", sa.Float(), nullable=True),
        sa.Column("benchmark_observations", sa.Integer(), nullable=False),
        sa.Column("average_max_favorable_pct", sa.Float(), nullable=True),
        sa.Column("average_max_adverse_pct", sa.Float(), nullable=True),
        sa.Column("universe_size", sa.Integer(), nullable=False),
        sa.Column(
            "point_in_time_complete", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("warning_text", sa.String(500), nullable=True),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "evidence_mode IN ('forward', 'reconstructed')",
            name="ck_research_condition_calibrations_evidence_mode",
        ),
        sa.CheckConstraint(
            "horizon_sessions IN (1, 5, 20, 60)",
            name="ck_research_condition_calibrations_horizon",
        ),
        sa.CheckConstraint(
            "observations >= 0 AND matured >= 0 AND pending >= 0 "
            "AND observations = matured + pending AND universe_size >= 0",
            name="ck_research_condition_calibrations_counts",
        ),
        sa.PrimaryKeyConstraint(
            "market",
            "condition_key",
            "condition_version",
            "methodology_version",
            "evidence_mode",
            "horizon_sessions",
        ),
    )
    op.create_index(
        "ix_research_condition_calibrations_market_date",
        _CALIBRATIONS,
        ["market", "as_of_date"],
    )

    op.create_table(
        _SUBSCRIPTIONS,
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("condition_key", sa.String(48), nullable=False),
        sa.Column("condition_version", sa.String(24), nullable=False),
        sa.Column("methodology_version", sa.String(48), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("last_alerted_on", sa.Date(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_atlas_condition_subscriptions_user_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["market", "code"],
            ["symbols.market", "symbols.code"],
            name="fk_atlas_condition_subscriptions_symbol",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "user_id",
            "market",
            "code",
            "condition_key",
            "condition_version",
            "methodology_version",
        ),
    )
    op.create_index(
        "ix_atlas_condition_subscriptions_dispatch",
        _SUBSCRIPTIONS,
        ["tenant_id", "market", "code", "condition_key", "enabled"],
    )
    predicate = "tenant_id = current_setting('app.tenant_id', true)"
    op.execute(sa.text(f'ALTER TABLE "{_SUBSCRIPTIONS}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{_SUBSCRIPTIONS}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f'CREATE POLICY "{_SUBSCRIPTIONS}_tenant_isolation" ON "{_SUBSCRIPTIONS}" '
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(f'DROP POLICY IF EXISTS "{_SUBSCRIPTIONS}_tenant_isolation" ON "{_SUBSCRIPTIONS}"')
    )
    op.execute(sa.text(f'ALTER TABLE "{_SUBSCRIPTIONS}" NO FORCE ROW LEVEL SECURITY'))
    op.drop_index("ix_atlas_condition_subscriptions_dispatch", table_name=_SUBSCRIPTIONS)
    op.drop_table(_SUBSCRIPTIONS)
    op.drop_index("ix_research_condition_calibrations_market_date", table_name=_CALIBRATIONS)
    op.drop_table(_CALIBRATIONS)
    op.drop_index(
        "ix_research_condition_transitions_market_code_condition", table_name=_TRANSITIONS
    )
    op.drop_index(
        "ix_research_condition_transitions_market_condition_date", table_name=_TRANSITIONS
    )
    op.drop_table(_TRANSITIONS)
