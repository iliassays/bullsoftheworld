"""Shared official evidence and tenant-safe research lineage."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
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


class EvidenceDocument(Base):
    """An immutable official source shared within one branded market tenant.

    Customer-private uploads use a separate store in a later delivery phase. Keeping them out of
    this table prevents public SEC/DSE documents from being copied once per organization while the
    tenant/market composite key prevents cross-market retrieval.
    """

    __tablename__ = "research_evidence_documents"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "tenant_id",
            "market",
            name="uq_research_evidence_documents_security_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "market",
            "source_type",
            "source_record_id",
            "source_revision",
            name="uq_research_evidence_documents_source_revision",
        ),
        CheckConstraint("source_revision <> ''", name="ck_research_evidence_source_revision"),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_research_evidence_content_hash",
        ),
        Index(
            "ix_research_evidence_documents_tenant_security_known",
            "tenant_id",
            "market",
            "code",
            "known_at",
        ),
        Index(
            "ix_research_evidence_documents_tenant_content_hash",
            "tenant_id",
            "market",
            "content_hash",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    source_type: Mapped[str] = mapped_column(String(48))
    source_record_id: Mapped[str] = mapped_column(String(192))
    source_revision: Mapped[str] = mapped_column(String(96))
    code: Mapped[str | None] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    effective_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    known_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    object_key: Mapped[str | None] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(String(96), default="text/plain")
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class ResearchRunEvidence(Base):
    """The complete evidence pack considered by a research run, including rejected material."""

    __tablename__ = "research_run_evidence"
    __table_args__ = (
        UniqueConstraint("run_id", "ordinal", name="uq_research_run_evidence_run_ordinal"),
        CheckConstraint("ordinal >= 0", name="ck_research_run_evidence_ordinal"),
        CheckConstraint(
            "disposition IN ('selected', 'rejected', 'unused')",
            name="ck_research_run_evidence_disposition",
        ),
        CheckConstraint(
            "purpose IS NULL OR purpose IN ('supporting', 'counter', 'context', 'calculation')",
            name="ck_research_run_evidence_purpose",
        ),
        ForeignKeyConstraint(
            ["run_id", "organization_id", "tenant_id", "market"],
            [
                "research_runs.id",
                "research_runs.organization_id",
                "research_runs.tenant_id",
                "research_runs.market",
            ],
            name="fk_research_run_evidence_run_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["evidence_document_id", "tenant_id", "market"],
            [
                "research_evidence_documents.id",
                "research_evidence_documents.tenant_id",
                "research_evidence_documents.market",
            ],
            name="fk_research_run_evidence_document_scope",
            ondelete="RESTRICT",
        ),
        Index("ix_research_run_evidence_document", "evidence_document_id"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    evidence_document_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    ordinal: Mapped[int] = mapped_column(Integer)
    disposition: Mapped[str] = mapped_column(String(16))
    purpose: Mapped[str | None] = mapped_column(String(16))
    retrieval_method: Mapped[str] = mapped_column(String(48))
    retrieval_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    rerank_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    rationale: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class EvidenceSpan(Base):
    __tablename__ = "research_evidence_spans"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "tenant_id",
            "market",
            name="uq_research_evidence_spans_security_scope",
        ),
        UniqueConstraint(
            "document_id", "ordinal", name="uq_research_evidence_spans_document_ordinal"
        ),
        CheckConstraint("ordinal >= 0", name="ck_research_evidence_spans_ordinal"),
        CheckConstraint("token_count >= 0", name="ck_research_evidence_spans_token_count"),
        CheckConstraint(
            "text_hash ~ '^[0-9a-f]{64}$'",
            name="ck_research_evidence_spans_text_hash",
        ),
        ForeignKeyConstraint(
            ["document_id", "tenant_id", "market"],
            [
                "research_evidence_documents.id",
                "research_evidence_documents.tenant_id",
                "research_evidence_documents.market",
            ],
            name="fk_research_evidence_spans_document_scope",
            ondelete="CASCADE",
        ),
        Index("ix_research_evidence_spans_document", "document_id", "ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    ordinal: Mapped[int] = mapped_column(Integer)
    locator: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64))
    token_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class ResearchClaim(Base):
    __tablename__ = "research_claims"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_claims_security_scope",
        ),
        UniqueConstraint("run_id", "ordinal", name="uq_research_claims_run_ordinal"),
        CheckConstraint("ordinal >= 0", name="ck_research_claims_ordinal"),
        CheckConstraint(
            "verdict IN ('supported', 'mixed', 'unsupported', 'unknown')",
            name="ck_research_claims_verdict",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_research_claims_confidence",
        ),
        ForeignKeyConstraint(
            ["run_id", "organization_id", "tenant_id", "market"],
            [
                "research_runs.id",
                "research_runs.organization_id",
                "research_runs.tenant_id",
                "research_runs.market",
            ],
            name="fk_research_claims_run_scope",
            ondelete="CASCADE",
        ),
        Index("ix_research_claims_run_verdict", "run_id", "verdict"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    ordinal: Mapped[int] = mapped_column(Integer)
    claim_type: Mapped[str] = mapped_column(String(48))
    statement: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    as_of_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    values: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    verification: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class ResearchClaimCitation(Base):
    __tablename__ = "research_claim_citations"
    __table_args__ = (
        CheckConstraint(
            "relation IN ('supports', 'contradicts', 'context')",
            name="ck_research_claim_citations_relation",
        ),
        CheckConstraint(
            "relevance >= 0 AND relevance <= 1",
            name="ck_research_claim_citations_relevance",
        ),
        ForeignKeyConstraint(
            ["claim_id", "organization_id", "tenant_id", "market"],
            [
                "research_claims.id",
                "research_claims.organization_id",
                "research_claims.tenant_id",
                "research_claims.market",
            ],
            name="fk_research_claim_citations_claim_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["evidence_span_id", "tenant_id", "market"],
            [
                "research_evidence_spans.id",
                "research_evidence_spans.tenant_id",
                "research_evidence_spans.market",
            ],
            name="fk_research_claim_citations_evidence_span_scope",
            ondelete="RESTRICT",
        ),
        Index("ix_research_claim_citations_evidence_span", "evidence_span_id"),
    )

    claim_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    evidence_span_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    relation: Mapped[str] = mapped_column(String(16), default="supports")
    relevance: Mapped[Decimal] = mapped_column(Numeric(5, 4))
