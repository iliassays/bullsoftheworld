"""Licensed research-dataset entitlements and immutable snapshot manifests."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class ResearchDataEntitlement(Base):
    """One approved usage contract for a dataset within a branded market tenant.

    There is intentionally no customer-organization key. These records describe platform-level
    vendor rights. Organization-private derived artifacts remain scoped through research runs.
    """

    __tablename__ = "research_data_entitlements"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "tenant_id",
            "market",
            "dataset_key",
            name="uq_research_data_entitlements_dataset_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "market",
            "dataset_key",
            name="uq_research_data_entitlements_dataset",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'suspended', 'expired')",
            name="ck_research_data_entitlements_status",
        ),
        CheckConstraint("dataset_key <> ''", name="ck_research_data_entitlements_dataset_key"),
        CheckConstraint("provider <> ''", name="ck_research_data_entitlements_provider"),
        CheckConstraint(
            "terms_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_research_data_entitlements_terms_hash",
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_from <= valid_until",
            name="ck_research_data_entitlements_validity",
        ),
        Index(
            "ix_research_data_entitlements_tenant_status",
            "tenant_id",
            "market",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    dataset_key: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(96))
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    internal_research_allowed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    customer_display_allowed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    derived_display_allowed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    redistribution_allowed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    retention_allowed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    valid_from: Mapped[dt.date | None] = mapped_column(Date)
    valid_until: Mapped[dt.date | None] = mapped_column(Date)
    agreement_reference: Mapped[str] = mapped_column(String(160))
    terms_sha256: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[str | None] = mapped_column(String(160))
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ResearchDatasetSnapshot(Base):
    """Immutable manifest for one raw and normalized research-dataset delivery."""

    __tablename__ = "research_dataset_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
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
        UniqueConstraint(
            "tenant_id",
            "market",
            "dataset_key",
            "trade_date",
            "completeness",
            "source_revision",
            name="uq_research_dataset_snapshots_revision",
        ),
        CheckConstraint(
            "status IN ('accepted', 'rejected')",
            name="ck_research_dataset_snapshots_status",
        ),
        CheckConstraint(
            "completeness IN ('preliminary', 'complete', 'sample')",
            name="ck_research_dataset_snapshots_completeness",
        ),
        CheckConstraint("row_count >= 0", name="ck_research_dataset_snapshots_row_count"),
        CheckConstraint(
            "source_revision <> ''",
            name="ck_research_dataset_snapshots_source_revision",
        ),
        CheckConstraint(
            "raw_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_research_dataset_snapshots_raw_hash",
        ),
        CheckConstraint(
            "normalized_sha256 IS NULL OR normalized_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_research_dataset_snapshots_normalized_hash",
        ),
        CheckConstraint(
            "dataset_fingerprint IS NULL OR dataset_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_research_dataset_snapshots_fingerprint",
        ),
        Index(
            "ix_research_dataset_snapshots_tenant_dataset_date",
            "tenant_id",
            "market",
            "dataset_key",
            "trade_date",
        ),
        Index(
            "ix_research_dataset_snapshots_status_known",
            "tenant_id",
            "market",
            "status",
            "known_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    entitlement_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    dataset_key: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(96))
    trade_date: Mapped[dt.date] = mapped_column(Date)
    completeness: Mapped[str] = mapped_column(String(16))
    source_revision: Mapped[str] = mapped_column(String(96))
    schema_version: Mapped[str] = mapped_column(String(48))
    normalization_version: Mapped[str] = mapped_column(String(48))
    identity_version: Mapped[str] = mapped_column(String(48))
    effective_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    known_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(16))
    row_count: Mapped[int] = mapped_column(Integer)
    raw_object_key: Mapped[str] = mapped_column(Text)
    raw_sha256: Mapped[str] = mapped_column(String(64))
    normalized_object_key: Mapped[str | None] = mapped_column(Text)
    normalized_sha256: Mapped[str | None] = mapped_column(String(64))
    dataset_fingerprint: Mapped[str | None] = mapped_column(String(64))
    quality_report: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    source_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ResearchDatasetEvaluation(Base):
    """Append-only manifest for a reproducible evaluation over immutable snapshots."""

    __tablename__ = "research_dataset_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "market",
            "dataset_key",
            "start_date",
            "end_date",
            "methodology_version",
            "input_fingerprint",
            name="uq_research_dataset_evaluations_input",
        ),
        CheckConstraint(
            "decision IN ('insufficient_data', 'quality_review_required', "
            "'ready_for_phase_b_review')",
            name="ck_research_dataset_evaluations_decision",
        ),
        CheckConstraint(
            "start_date <= end_date",
            name="ck_research_dataset_evaluations_date_range",
        ),
        CheckConstraint(
            "canonical_snapshot_count >= 0",
            name="ck_research_dataset_evaluations_snapshot_count",
        ),
        CheckConstraint(
            "input_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_research_dataset_evaluations_input_hash",
        ),
        CheckConstraint(
            "report_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_research_dataset_evaluations_report_hash",
        ),
        Index(
            "ix_research_dataset_evaluations_tenant_dataset_period",
            "tenant_id",
            "market",
            "dataset_key",
            "start_date",
            "end_date",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    dataset_key: Mapped[str] = mapped_column(String(64))
    start_date: Mapped[dt.date] = mapped_column(Date)
    end_date: Mapped[dt.date] = mapped_column(Date)
    methodology_version: Mapped[str] = mapped_column(String(64))
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    generated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    decision: Mapped[str] = mapped_column(String(32))
    canonical_snapshot_count: Mapped[int] = mapped_column(Integer)
    report_object_key: Mapped[str] = mapped_column(Text)
    report_sha256: Mapped[str] = mapped_column(String(64))
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
