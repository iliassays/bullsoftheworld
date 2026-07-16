"""US options Phase A entitlements and immutable dataset manifests.

Revision ID: d2a4c6e8f0b1
Revises: c9e1f3a5b7d9
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d2a4c6e8f0b1"
down_revision = "c9e1f3a5b7d9"
branch_labels = None
depends_on = None

_ENTITLEMENTS = "research_data_entitlements"
_SNAPSHOTS = "research_dataset_snapshots"
_EVALUATIONS = "research_dataset_evaluations"
_TENANT_SCOPE = (
    "tenant_id = current_setting('app.research_tenant_id', true) "
    "AND market = current_setting('app.research_market', true)"
)


def _enable_rls(table: str) -> None:
    policy = f"{table}_tenant_market_isolation"
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f'CREATE POLICY "{policy}" ON "{table}" '
            f"USING ({_TENANT_SCOPE}) WITH CHECK ({_TENANT_SCOPE})"
        )
    )


def upgrade() -> None:
    op.create_table(
        _ENTITLEMENTS,
        sa.Column("id", sa.Uuid(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("dataset_key", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(96), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column(
            "internal_research_allowed", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column(
            "customer_display_allowed", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column(
            "derived_display_allowed", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column(
            "redistribution_allowed", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("retention_allowed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("agreement_reference", sa.String(160), nullable=False),
        sa.Column("terms_sha256", sa.String(64), nullable=False),
        sa.Column("approved_by", sa.String(160), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'suspended', 'expired')",
            name="ck_research_data_entitlements_status",
        ),
        sa.CheckConstraint(
            "dataset_key <> ''", name="ck_research_data_entitlements_dataset_key"
        ),
        sa.CheckConstraint("provider <> ''", name="ck_research_data_entitlements_provider"),
        sa.CheckConstraint(
            "terms_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_research_data_entitlements_terms_hash",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_from <= valid_until",
            name="ck_research_data_entitlements_validity",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "market",
            "dataset_key",
            name="uq_research_data_entitlements_dataset_scope",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "market",
            "dataset_key",
            name="uq_research_data_entitlements_dataset",
        ),
    )
    op.create_index(
        "ix_research_data_entitlements_tenant_status",
        _ENTITLEMENTS,
        ["tenant_id", "market", "status"],
    )

    op.create_table(
        _SNAPSHOTS,
        sa.Column("id", sa.Uuid(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("entitlement_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_key", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(96), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("completeness", sa.String(16), nullable=False),
        sa.Column("source_revision", sa.String(96), nullable=False),
        sa.Column("schema_version", sa.String(48), nullable=False),
        sa.Column("normalization_version", sa.String(48), nullable=False),
        sa.Column("identity_version", sa.String(48), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("raw_object_key", sa.Text(), nullable=False),
        sa.Column("raw_sha256", sa.String(64), nullable=False),
        sa.Column("normalized_object_key", sa.Text(), nullable=True),
        sa.Column("normalized_sha256", sa.String(64), nullable=True),
        sa.Column("dataset_fingerprint", sa.String(64), nullable=True),
        sa.Column(
            "quality_report",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "source_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('accepted', 'rejected')",
            name="ck_research_dataset_snapshots_status",
        ),
        sa.CheckConstraint(
            "completeness IN ('preliminary', 'complete', 'sample')",
            name="ck_research_dataset_snapshots_completeness",
        ),
        sa.CheckConstraint(
            "row_count >= 0", name="ck_research_dataset_snapshots_row_count"
        ),
        sa.CheckConstraint(
            "source_revision <> ''",
            name="ck_research_dataset_snapshots_source_revision",
        ),
        sa.CheckConstraint(
            "raw_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_research_dataset_snapshots_raw_hash",
        ),
        sa.CheckConstraint(
            "normalized_sha256 IS NULL OR normalized_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_research_dataset_snapshots_normalized_hash",
        ),
        sa.CheckConstraint(
            "dataset_fingerprint IS NULL OR dataset_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_research_dataset_snapshots_fingerprint",
        ),
        sa.ForeignKeyConstraint(
            ["entitlement_id", "tenant_id", "market", "dataset_key"],
            [
                "research_data_entitlements.id",
                "research_data_entitlements.tenant_id",
                "research_data_entitlements.market",
                "research_data_entitlements.dataset_key",
            ],
            name="fk_research_dataset_snapshots_entitlement_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "market",
            "dataset_key",
            "trade_date",
            "completeness",
            "source_revision",
            name="uq_research_dataset_snapshots_revision",
        ),
    )
    op.create_index(
        "ix_research_dataset_snapshots_tenant_dataset_date",
        _SNAPSHOTS,
        ["tenant_id", "market", "dataset_key", "trade_date"],
    )
    op.create_index(
        "ix_research_dataset_snapshots_status_known",
        _SNAPSHOTS,
        ["tenant_id", "market", "status", "known_at"],
    )

    op.create_table(
        _EVALUATIONS,
        sa.Column("id", sa.Uuid(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("dataset_key", sa.String(64), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("methodology_version", sa.String(64), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("canonical_snapshot_count", sa.Integer(), nullable=False),
        sa.Column("report_object_key", sa.Text(), nullable=False),
        sa.Column("report_sha256", sa.String(64), nullable=False),
        sa.Column(
            "summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "decision IN ('insufficient_data', 'quality_review_required', "
            "'ready_for_phase_b_review')",
            name="ck_research_dataset_evaluations_decision",
        ),
        sa.CheckConstraint(
            "start_date <= end_date",
            name="ck_research_dataset_evaluations_date_range",
        ),
        sa.CheckConstraint(
            "canonical_snapshot_count >= 0",
            name="ck_research_dataset_evaluations_snapshot_count",
        ),
        sa.CheckConstraint(
            "input_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_research_dataset_evaluations_input_hash",
        ),
        sa.CheckConstraint(
            "report_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_research_dataset_evaluations_report_hash",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "market",
            "dataset_key",
            "start_date",
            "end_date",
            "methodology_version",
            "input_fingerprint",
            name="uq_research_dataset_evaluations_input",
        ),
    )
    op.create_index(
        "ix_research_dataset_evaluations_tenant_dataset_period",
        _EVALUATIONS,
        ["tenant_id", "market", "dataset_key", "start_date", "end_date"],
    )

    _enable_rls(_ENTITLEMENTS)
    _enable_rls(_SNAPSHOTS)
    _enable_rls(_EVALUATIONS)
    op.execute(
        sa.text(
            "CREATE FUNCTION reject_research_dataset_artifact_mutation() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN "
            "RAISE EXCEPTION 'research dataset artifacts are append-only' "
            "USING ERRCODE = '55000'; "
            "END; $$"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER research_dataset_snapshots_append_only "
            f"BEFORE UPDATE OR DELETE ON {_SNAPSHOTS} "
            "FOR EACH ROW EXECUTE FUNCTION reject_research_dataset_artifact_mutation()"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER research_dataset_evaluations_append_only "
            f"BEFORE UPDATE OR DELETE ON {_EVALUATIONS} "
            "FOR EACH ROW EXECUTE FUNCTION reject_research_dataset_artifact_mutation()"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            f"DROP TRIGGER IF EXISTS research_dataset_evaluations_append_only ON {_EVALUATIONS}"
        )
    )
    op.execute(
        sa.text(
            f"DROP TRIGGER IF EXISTS research_dataset_snapshots_append_only ON {_SNAPSHOTS}"
        )
    )
    op.execute(
        sa.text("DROP FUNCTION IF EXISTS reject_research_dataset_artifact_mutation()")
    )
    for table in (_EVALUATIONS, _SNAPSHOTS, _ENTITLEMENTS):
        op.execute(
            sa.text(
                f'DROP POLICY IF EXISTS "{table}_tenant_market_isolation" ON "{table}"'
            )
        )
    op.drop_table(_EVALUATIONS)
    op.drop_table(_SNAPSHOTS)
    op.drop_table(_ENTITLEMENTS)
