"""Immutable research observations and resumable onboarding stages.

Revision ID: f6d8a0c2e4b7
Revises: d2a4c6e8f0b1
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f6d8a0c2e4b7"
down_revision = "d2a4c6e8f0b1"
branch_labels = None
depends_on = None

_SNAPSHOTS = "data_source_snapshots"
_BAR_OBSERVATIONS = "daily_bar_observations"
_LISTING_OBSERVATIONS = "security_listing_observations"
_SEC_OBSERVATIONS = "sec_financial_fact_observations"
_COMPANY_OBSERVATIONS = "company_data_observations"
_STAGES = "universe_onboarding_stages"
_IMMUTABLE_TABLES = (
    _SNAPSHOTS,
    _BAR_OBSERVATIONS,
    _LISTING_OBSERVATIONS,
    _SEC_OBSERVATIONS,
    _COMPANY_OBSERVATIONS,
)


def _json_object() -> sa.TextClause:
    return sa.text("'{}'::jsonb")


def upgrade() -> None:
    op.create_table(
        _SNAPSHOTS,
        sa.Column("id", sa.Uuid(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("dataset_key", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(96), nullable=False),
        sa.Column("scope_key", sa.String(96), nullable=False),
        sa.Column("source_revision", sa.String(96), nullable=False),
        sa.Column("schema_version", sa.String(48), nullable=False),
        sa.Column("normalization_version", sa.String(48), nullable=False),
        sa.Column("code_version", sa.String(96), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("raw_object_key", sa.Text(), nullable=True),
        sa.Column("raw_sha256", sa.String(64), nullable=True),
        sa.Column("normalized_sha256", sa.String(64), nullable=False),
        sa.Column(
            "quality_report",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=_json_object(),
            nullable=False,
        ),
        sa.Column(
            "source_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=_json_object(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('accepted', 'rejected')", name="ck_data_source_snapshots_status"
        ),
        sa.CheckConstraint("row_count >= 0", name="ck_data_source_snapshots_row_count"),
        sa.CheckConstraint(
            "raw_sha256 IS NULL OR raw_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_data_source_snapshots_raw_hash",
        ),
        sa.CheckConstraint(
            "normalized_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_data_source_snapshots_normalized_hash",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "market",
            "dataset_key",
            "scope_key",
            "source_revision",
            name="uq_data_source_snapshots_revision",
        ),
    )
    op.create_index(
        "ix_data_source_snapshots_dataset_known",
        _SNAPSHOTS,
        ["market", "dataset_key", "known_at"],
    )

    op.create_table(
        _BAR_OBSERVATIONS,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("adjusted_close", sa.Float(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("knowledge_time_quality", sa.String(32), nullable=False),
        sa.Column("row_sha256", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "knowledge_time_quality IN ('source_published', 'ingestion_upper_bound', 'legacy_unknown')",
            name="ck_daily_bar_observations_knowledge_quality",
        ),
        sa.CheckConstraint(
            "row_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_daily_bar_observations_row_hash",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["data_source_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "market",
            "code",
            "date",
            "row_sha256",
            name="uq_daily_bar_observations_revision",
        ),
    )
    op.create_index(
        "ix_daily_bar_observations_symbol_date_known",
        _BAR_OBSERVATIONS,
        ["market", "code", "date", "known_at"],
    )

    op.create_table(
        _LISTING_OBSERVATIONS,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("event_kind", sa.String(12), nullable=False),
        sa.Column("security_name", sa.Text(), nullable=False),
        sa.Column("exchange", sa.String(32), nullable=True),
        sa.Column("cik", sa.Integer(), nullable=True),
        sa.Column("instrument_type", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_product_eligible", sa.Boolean(), nullable=False),
        sa.Column("exclude_reason", sa.String(64), nullable=True),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("row_sha256", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "event_kind IN ('added', 'updated', 'removed')",
            name="ck_security_listing_observations_event_kind",
        ),
        sa.CheckConstraint(
            "row_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_security_listing_observations_row_hash",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["data_source_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_snapshot_id",
            "market",
            "symbol",
            name="uq_security_listing_observations_snapshot_symbol",
        ),
    )
    op.create_index(
        "ix_security_listing_observations_identity_known",
        _LISTING_OBSERVATIONS,
        ["market", "symbol", "known_at"],
    )
    op.create_index(
        "ix_security_listing_observations_security_known",
        _LISTING_OBSERVATIONS,
        ["security_id", "known_at"],
    )

    op.create_table(
        _SEC_OBSERVATIONS,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("metric", sa.String(40), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(24), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("period_type", sa.String(12), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_period", sa.String(8), nullable=True),
        sa.Column("form", sa.String(16), nullable=False),
        sa.Column("filed_at", sa.Date(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accession_number", sa.String(25), nullable=False),
        sa.Column("taxonomy", sa.String(32), nullable=False),
        sa.Column("source_concept", sa.String(128), nullable=False),
        sa.Column("frame", sa.String(32), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("normalization_version", sa.String(48), nullable=False),
        sa.Column("row_sha256", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "period_type IN ('instant', 'quarter', 'annual', 'ytd')",
            name="ck_sec_financial_fact_observations_period_type",
        ),
        sa.CheckConstraint(
            "row_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_sec_financial_fact_observations_row_hash",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["data_source_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "market",
            "code",
            "metric",
            "period_end",
            "period_type",
            "accession_number",
            "row_sha256",
            name="uq_sec_financial_fact_observations_revision",
        ),
    )
    op.create_index(
        "ix_sec_financial_fact_observations_symbol_period_known",
        _SEC_OBSERVATIONS,
        ["market", "code", "period_end", "known_at"],
    )

    op.create_table(
        _COMPANY_OBSERVATIONS,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("record_type", sa.String(24), nullable=False),
        sa.Column("natural_key", sa.String(64), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("row_sha256", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "record_type IN ('profile', 'shareholding', 'annual_financial', 'dividend')",
            name="ck_company_data_observations_record_type",
        ),
        sa.CheckConstraint(
            "row_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_company_data_observations_row_hash",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["data_source_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "market",
            "code",
            "record_type",
            "natural_key",
            "row_sha256",
            name="uq_company_data_observations_revision",
        ),
    )
    op.create_index(
        "ix_company_data_observations_symbol_type_known",
        _COMPANY_OBSERVATIONS,
        ["market", "code", "record_type", "known_at"],
    )

    op.create_table(
        _STAGES,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("stage_key", sa.String(48), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="1", nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("output_fingerprint", sa.String(64), nullable=True),
        sa.Column(
            "stats",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=_json_object(),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_universe_onboarding_stage_status",
        ),
        sa.CheckConstraint(
            "input_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_universe_onboarding_stage_input_hash",
        ),
        sa.CheckConstraint(
            "output_fingerprint IS NULL OR output_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_universe_onboarding_stage_output_hash",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["universe_onboarding_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "stage_key", name="uq_universe_onboarding_stages_run_stage"),
    )
    op.create_index("ix_universe_onboarding_stages_run_ordinal", _STAGES, ["run_id", "ordinal"])

    op.add_column("ticker_analytics", sa.Column("methodology_version", sa.String(48)))
    op.add_column("ticker_analytics", sa.Column("input_fingerprint", sa.String(64)))
    op.add_column(
        "ticker_analytics",
        sa.Column("point_in_time_complete", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_check_constraint(
        "ck_ticker_analytics_input_fingerprint",
        "ticker_analytics",
        "input_fingerprint IS NULL OR input_fingerprint ~ '^[0-9a-f]{64}$'",
    )

    op.execute(
        sa.text(
            "CREATE FUNCTION reject_data_foundation_artifact_mutation() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN "
            "RAISE EXCEPTION 'data foundation artifacts are append-only' "
            "USING ERRCODE = '55000'; END; $$"
        )
    )
    for table in _IMMUTABLE_TABLES:
        op.execute(
            sa.text(
                f'CREATE TRIGGER "{table}_append_only" BEFORE UPDATE OR DELETE ON "{table}" '
                "FOR EACH ROW EXECUTE FUNCTION reject_data_foundation_artifact_mutation()"
            )
        )


def downgrade() -> None:
    for table in reversed(_IMMUTABLE_TABLES):
        op.execute(sa.text(f'DROP TRIGGER IF EXISTS "{table}_append_only" ON "{table}"'))
    op.execute(sa.text("DROP FUNCTION IF EXISTS reject_data_foundation_artifact_mutation()"))
    op.drop_constraint("ck_ticker_analytics_input_fingerprint", "ticker_analytics", type_="check")
    op.drop_column("ticker_analytics", "point_in_time_complete")
    op.drop_column("ticker_analytics", "input_fingerprint")
    op.drop_column("ticker_analytics", "methodology_version")
    op.drop_table(_STAGES)
    op.drop_table(_COMPANY_OBSERVATIONS)
    op.drop_table(_SEC_OBSERVATIONS)
    op.drop_table(_LISTING_OBSERVATIONS)
    op.drop_table(_BAR_OBSERVATIONS)
    op.drop_table(_SNAPSHOTS)
