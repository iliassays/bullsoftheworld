"""Persist immutable, versioned research-universe policy decisions.

Revision ID: e5a7c9b1d3f5
Revises: d4e7f9a1c3b5
Create Date: 2026-08-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e5a7c9b1d3f5"
down_revision = "d4e7f9a1c3b5"
branch_labels = None
depends_on = None

_SNAPSHOTS = "research_universe_snapshots"
_MEMBERS = "research_universe_members"


def _json_object() -> sa.TextClause:
    return sa.text("'{}'::jsonb")


def _json_array() -> sa.TextClause:
    return sa.text("'[]'::jsonb")


def upgrade() -> None:
    op.create_table(
        _SNAPSHOTS,
        sa.Column("id", sa.Uuid(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("knowledge_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_key", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(32), nullable=False),
        sa.Column("policy_sha256", sa.String(64), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("source_mode", sa.String(24), nullable=False),
        sa.Column("model_ready", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("eligible_count", sa.Integer(), nullable=False),
        sa.Column("ineligible_count", sa.Integer(), nullable=False),
        sa.Column("data_blocked_count", sa.Integer(), nullable=False),
        sa.Column("model_eligible_count", sa.Integer(), nullable=False),
        sa.Column(
            "policy_parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=_json_object(),
            nullable=False,
        ),
        sa.Column(
            "quality_report",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=_json_object(),
            nullable=False,
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_mode IN ('point_in_time', 'current_projection')",
            name="ck_research_universe_snapshots_source_mode",
        ),
        sa.CheckConstraint(
            "market IN ('DSE', 'US')",
            name="ck_research_universe_snapshots_market",
        ),
        sa.CheckConstraint(
            "candidate_count >= 0 AND eligible_count >= 0 AND ineligible_count >= 0 "
            "AND data_blocked_count >= 0 AND model_eligible_count >= 0 "
            "AND candidate_count = eligible_count + ineligible_count + data_blocked_count "
            "AND model_eligible_count <= eligible_count",
            name="ck_research_universe_snapshots_counts",
        ),
        sa.CheckConstraint(
            "NOT model_ready OR (eligible_count > 0 AND data_blocked_count = 0 "
            "AND model_eligible_count = eligible_count)",
            name="ck_research_universe_snapshots_model_ready",
        ),
        sa.CheckConstraint(
            "policy_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_research_universe_snapshots_policy_hash",
        ),
        sa.CheckConstraint(
            "input_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_research_universe_snapshots_input_hash",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "market",
            name="uq_research_universe_snapshots_market_scope",
        ),
        sa.UniqueConstraint(
            "market",
            "as_of_date",
            "policy_key",
            "policy_version",
            "input_fingerprint",
            name="uq_research_universe_snapshots_input",
        ),
    )
    op.create_index(
        "ix_research_universe_snapshots_market_date",
        _SNAPSHOTS,
        ["market", "as_of_date"],
    )
    op.create_index(
        "ix_research_universe_snapshots_market_policy",
        _SNAPSHOTS,
        ["market", "policy_key", "policy_version"],
    )

    op.create_table(
        _MEMBERS,
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=True),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("cohort", sa.String(32), nullable=True),
        sa.Column("cap_tier", sa.String(16), nullable=True),
        sa.Column("model_eligible", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "reason_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=_json_array(),
            nullable=False,
        ),
        sa.Column(
            "model_blocker_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=_json_array(),
            nullable=False,
        ),
        sa.Column(
            "warning_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=_json_array(),
            nullable=False,
        ),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=_json_object(),
            nullable=False,
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=_json_object(),
            nullable=False,
        ),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('eligible', 'ineligible', 'data_blocked')",
            name="ck_research_universe_members_decision",
        ),
        sa.CheckConstraint(
            "market IN ('DSE', 'US')",
            name="ck_research_universe_members_market",
        ),
        sa.CheckConstraint(
            "(market = 'DSE' AND (cohort IS NULL OR cohort = 'dse_liquid')) OR "
            "(market = 'US' AND (cohort IS NULL OR cohort IN "
            "('us_core', 'us_small', 'us_micro_penny')))",
            name="ck_research_universe_members_market_cohort",
        ),
        sa.CheckConstraint(
            "input_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_research_universe_members_input_hash",
        ),
        sa.CheckConstraint(
            "NOT model_eligible OR decision = 'eligible'",
            name="ck_research_universe_members_model_eligibility",
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["security_master.security_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "market"],
            ["research_universe_snapshots.id", "research_universe_snapshots.market"],
            name="fk_research_universe_members_snapshot_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("snapshot_id", "market", "code"),
    )
    op.create_index(
        "ix_research_universe_members_snapshot_decision",
        _MEMBERS,
        ["snapshot_id", "decision", "cohort"],
    )
    op.create_index(
        "ix_research_universe_members_market_code",
        _MEMBERS,
        ["market", "code"],
    )
    op.execute(
        sa.text(
            "CREATE FUNCTION reject_research_universe_mutation() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN "
            "RAISE EXCEPTION 'research universe snapshots are append-only'; END; $$"
        )
    )
    for table in (_SNAPSHOTS, _MEMBERS):
        op.execute(
            sa.text(
                f"CREATE TRIGGER {table}_append_only "
                f"BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION reject_research_universe_mutation()"
            )
        )


def downgrade() -> None:
    for table in (_MEMBERS, _SNAPSHOTS):
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS reject_research_universe_mutation()"))
    op.drop_index("ix_research_universe_members_market_code", table_name=_MEMBERS)
    op.drop_index("ix_research_universe_members_snapshot_decision", table_name=_MEMBERS)
    op.drop_table(_MEMBERS)
    op.drop_index("ix_research_universe_snapshots_market_policy", table_name=_SNAPSHOTS)
    op.drop_index("ix_research_universe_snapshots_market_date", table_name=_SNAPSHOTS)
    op.drop_table(_SNAPSHOTS)
