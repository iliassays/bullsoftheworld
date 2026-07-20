"""Append-only EDGAR filing-event stream (market-wide, capture-timestamped).

Unlike ``sec.py``'s per-tracked-company projections, these tables record *what was
filed, by anyone, and when we captured it* — the point-in-time contract the
filings-event research needs (institutional study, Phase 14 Stage 0.1). Rows are
append-only; the raw dissemination bytes live in the immutable object store keyed by
``raw_sha256``, so any parse can be re-run historically and replayed byte-identically.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class EdgarFilingEvent(Base):
    """One filing seen on an EDGAR daily index: the capture log for the stream."""

    __tablename__ = "edgar_filing_events"
    __table_args__ = (
        CheckConstraint(
            "parse_status IN ('pending', 'parsed', 'failed', 'skipped')",
            name="ck_edgar_filing_events_parse_status",
        ),
        CheckConstraint(
            "raw_sha256 IS NULL OR raw_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_edgar_filing_events_raw_hash",
        ),
        Index("ix_edgar_filing_events_form_date", "form", "filed_date"),
        Index("ix_edgar_filing_events_cik_date", "cik", "filed_date"),
    )

    accession_number: Mapped[str] = mapped_column(String(25), primary_key=True)
    market: Mapped[str] = mapped_column(String(8), default="US")
    form: Mapped[str] = mapped_column(String(16), index=True)
    cik: Mapped[int] = mapped_column(BigInteger, index=True)
    company_name: Mapped[str | None] = mapped_column(Text)
    filed_date: Mapped[dt.date] = mapped_column(Date, index=True)
    accepted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # When *we* first knew about the filing — the honesty anchor for event studies.
    captured_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    index_filename: Mapped[str] = mapped_column(Text)
    raw_object_key: Mapped[str | None] = mapped_column(Text)
    raw_sha256: Mapped[str | None] = mapped_column(String(64))
    parse_status: Mapped[str] = mapped_column(String(16), default="pending")


class InsiderTransaction(Base):
    """One parsed non-derivative Form 4 transaction row (Section 16)."""

    __tablename__ = "insider_transactions"
    __table_args__ = (
        UniqueConstraint(
            "accession_number",
            "owner_cik",
            "row_index",
            name="uq_insider_transactions_row",
        ),
        Index("ix_insider_transactions_issuer_date", "issuer_cik", "transaction_date"),
        Index("ix_insider_transactions_code_date", "code", "transaction_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    accession_number: Mapped[str] = mapped_column(String(25), index=True)
    row_index: Mapped[int] = mapped_column(Integer)
    issuer_cik: Mapped[int] = mapped_column(BigInteger, index=True)
    issuer_symbol: Mapped[str | None] = mapped_column(String(16), index=True)
    issuer_name: Mapped[str | None] = mapped_column(Text)
    owner_cik: Mapped[int] = mapped_column(BigInteger, index=True)
    owner_name: Mapped[str | None] = mapped_column(Text)
    is_director: Mapped[bool] = mapped_column(Boolean, default=False)
    is_officer: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ten_percent_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    officer_title: Mapped[str | None] = mapped_column(Text)
    # The 2023 checkbox: scheduled-plan trades are dropped by the research filter.
    is_10b5_1_plan: Mapped[bool] = mapped_column(Boolean, default=False)
    security_title: Mapped[str | None] = mapped_column(Text)
    transaction_date: Mapped[dt.date | None] = mapped_column(Date)
    code: Mapped[str | None] = mapped_column(String(4))
    shares: Mapped[float | None] = mapped_column(Float)
    price_per_share: Mapped[float | None] = mapped_column(Float)
    acquired_disposed: Mapped[str | None] = mapped_column(String(1))
    shares_owned_after: Mapped[float | None] = mapped_column(Float)
    direct_or_indirect: Mapped[str | None] = mapped_column(String(1))
    # When set, the filing also carried derivative rows this table does not model —
    # the parsed share counts never describe the whole filing in that case.
    has_derivative_transactions: Mapped[bool] = mapped_column(Boolean, default=False)
    captured_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OwnershipStakeEvent(Base):
    """One parsed Schedule 13D/13G event (subject, filer, acceptance time)."""

    __tablename__ = "ownership_stake_events"
    __table_args__ = (
        Index("ix_ownership_stake_events_subject_date", "subject_cik", "filed_date"),
        Index("ix_ownership_stake_events_filer_date", "filed_by_cik", "filed_date"),
    )

    accession_number: Mapped[str] = mapped_column(String(25), primary_key=True)
    form: Mapped[str] = mapped_column(String(16), index=True)
    subject_cik: Mapped[int] = mapped_column(BigInteger, index=True)
    subject_name: Mapped[str] = mapped_column(Text)
    filed_by_cik: Mapped[int | None] = mapped_column(BigInteger, index=True)
    filed_by_name: Mapped[str | None] = mapped_column(Text)
    filed_date: Mapped[dt.date | None] = mapped_column(Date, index=True)
    accepted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # Best-effort cover-page scrape; None is a valid answer, never a guess.
    percent_of_class: Mapped[float | None] = mapped_column(Float)
    captured_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
