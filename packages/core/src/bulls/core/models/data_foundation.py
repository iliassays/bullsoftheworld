"""Immutable lineage and observations behind the mutable product projections.

The portal reads compact current-state tables such as ``daily_bars`` and
``company_profiles``. Research needs a different contract: every accepted source
delivery and every materially different observation is retained with the time at
which the platform could first know it. These tables provide that contract without
making operational reads slower.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
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


class DataSourceSnapshot(Base):
    """Immutable manifest for one accepted normalized source delivery.

    ``raw_*`` is nullable by design. Some public adapters currently expose only
    parsed records. That limitation is recorded honestly instead of inventing raw
    lineage; ``normalized_sha256`` still makes every persisted projection
    reproducible from the accepted in-memory delivery.
    """

    __tablename__ = "data_source_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "market",
            "dataset_key",
            "scope_key",
            "source_revision",
            name="uq_data_source_snapshots_revision",
        ),
        CheckConstraint(
            "status IN ('accepted', 'rejected')",
            name="ck_data_source_snapshots_status",
        ),
        CheckConstraint("row_count >= 0", name="ck_data_source_snapshots_row_count"),
        CheckConstraint(
            "raw_sha256 IS NULL OR raw_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_data_source_snapshots_raw_hash",
        ),
        CheckConstraint(
            "normalized_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_data_source_snapshots_normalized_hash",
        ),
        Index(
            "ix_data_source_snapshots_dataset_known",
            "market",
            "dataset_key",
            "known_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    market: Mapped[str] = mapped_column(String(8))
    dataset_key: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(96))
    scope_key: Mapped[str] = mapped_column(String(96))
    source_revision: Mapped[str] = mapped_column(String(96))
    schema_version: Mapped[str] = mapped_column(String(48))
    normalization_version: Mapped[str] = mapped_column(String(48))
    code_version: Mapped[str] = mapped_column(String(96))
    effective_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    known_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(16), default="accepted")
    row_count: Mapped[int] = mapped_column(Integer)
    raw_object_key: Mapped[str | None] = mapped_column(Text)
    raw_sha256: Mapped[str | None] = mapped_column(String(64))
    normalized_sha256: Mapped[str] = mapped_column(String(64))
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


class DailyBarObservation(Base):
    """Append-only revisions of an EOD bar; ``daily_bars`` is the current projection."""

    __tablename__ = "daily_bar_observations"
    __table_args__ = (
        UniqueConstraint(
            "market",
            "code",
            "date",
            "row_sha256",
            name="uq_daily_bar_observations_revision",
        ),
        CheckConstraint(
            "knowledge_time_quality IN ('source_published', 'ingestion_upper_bound', 'legacy_unknown')",
            name="ck_daily_bar_observations_knowledge_quality",
        ),
        CheckConstraint(
            "row_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_daily_bar_observations_row_hash",
        ),
        Index(
            "ix_daily_bar_observations_symbol_date_known",
            "market",
            "code",
            "date",
            "known_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("data_source_snapshots.id", ondelete="RESTRICT"),
    )
    market: Mapped[str] = mapped_column(String(8))
    code: Mapped[str] = mapped_column(String(16))
    date: Mapped[dt.date] = mapped_column(Date)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(BigInteger)
    adjusted_close: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32))
    known_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    knowledge_time_quality: Mapped[str] = mapped_column(String(32))
    row_sha256: Mapped[str] = mapped_column(String(64))


class SecurityListingObservation(Base):
    """Append-only listing/identity changes used to reconstruct a historical universe."""

    __tablename__ = "security_listing_observations"
    __table_args__ = (
        UniqueConstraint(
            "source_snapshot_id",
            "market",
            "symbol",
            name="uq_security_listing_observations_snapshot_symbol",
        ),
        CheckConstraint(
            "event_kind IN ('added', 'updated', 'removed')",
            name="ck_security_listing_observations_event_kind",
        ),
        CheckConstraint(
            "row_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_security_listing_observations_row_hash",
        ),
        Index(
            "ix_security_listing_observations_identity_known",
            "market",
            "symbol",
            "known_at",
        ),
        Index(
            "ix_security_listing_observations_security_known",
            "security_id",
            "known_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("data_source_snapshots.id", ondelete="RESTRICT"),
    )
    security_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    market: Mapped[str] = mapped_column(String(8))
    symbol: Mapped[str] = mapped_column(String(32))
    event_kind: Mapped[str] = mapped_column(String(12))
    security_name: Mapped[str] = mapped_column(Text)
    exchange: Mapped[str | None] = mapped_column(String(32))
    cik: Mapped[int | None] = mapped_column(Integer)
    instrument_type: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean)
    is_product_eligible: Mapped[bool] = mapped_column(Boolean)
    exclude_reason: Mapped[str | None] = mapped_column(String(64))
    known_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    row_sha256: Mapped[str] = mapped_column(String(64))


class SecFinancialFactObservation(Base):
    """Append-only SEC fact revisions retained before refreshing the current projection."""

    __tablename__ = "sec_financial_fact_observations"
    __table_args__ = (
        UniqueConstraint(
            "market",
            "code",
            "metric",
            "period_end",
            "period_type",
            "accession_number",
            "row_sha256",
            name="uq_sec_financial_fact_observations_revision",
        ),
        CheckConstraint(
            "period_type IN ('instant', 'quarter', 'annual', 'ytd')",
            name="ck_sec_financial_fact_observations_period_type",
        ),
        CheckConstraint(
            "row_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_sec_financial_fact_observations_row_hash",
        ),
        Index(
            "ix_sec_financial_fact_observations_symbol_period_known",
            "market",
            "code",
            "period_end",
            "known_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("data_source_snapshots.id", ondelete="RESTRICT"),
    )
    market: Mapped[str] = mapped_column(String(8))
    code: Mapped[str] = mapped_column(String(16))
    metric: Mapped[str] = mapped_column(String(40))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(24))
    period_start: Mapped[dt.date | None] = mapped_column(Date)
    period_end: Mapped[dt.date] = mapped_column(Date)
    period_type: Mapped[str] = mapped_column(String(12))
    fiscal_year: Mapped[int | None] = mapped_column(Integer)
    fiscal_period: Mapped[str | None] = mapped_column(String(8))
    form: Mapped[str] = mapped_column(String(16))
    filed_at: Mapped[dt.date] = mapped_column(Date)
    accepted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    accession_number: Mapped[str] = mapped_column(String(25))
    taxonomy: Mapped[str] = mapped_column(String(32))
    source_concept: Mapped[str] = mapped_column(String(128))
    frame: Mapped[str | None] = mapped_column(String(32))
    source_url: Mapped[str] = mapped_column(Text)
    known_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    normalization_version: Mapped[str] = mapped_column(String(48))
    row_sha256: Mapped[str] = mapped_column(String(64))


class CompanyDataObservation(Base):
    """Normalized DSE profile/fundamental/ownership revisions with conservative known time."""

    __tablename__ = "company_data_observations"
    __table_args__ = (
        UniqueConstraint(
            "market",
            "code",
            "record_type",
            "natural_key",
            "row_sha256",
            name="uq_company_data_observations_revision",
        ),
        CheckConstraint(
            "record_type IN ('profile', 'shareholding', 'annual_financial', 'dividend')",
            name="ck_company_data_observations_record_type",
        ),
        CheckConstraint(
            "row_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_company_data_observations_row_hash",
        ),
        Index(
            "ix_company_data_observations_symbol_type_known",
            "market",
            "code",
            "record_type",
            "known_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("data_source_snapshots.id", ondelete="RESTRICT"),
    )
    market: Mapped[str] = mapped_column(String(8))
    code: Mapped[str] = mapped_column(String(16))
    record_type: Mapped[str] = mapped_column(String(24))
    natural_key: Mapped[str] = mapped_column(String(64))
    effective_date: Mapped[dt.date | None] = mapped_column(Date)
    known_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    source: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    row_sha256: Mapped[str] = mapped_column(String(64))
