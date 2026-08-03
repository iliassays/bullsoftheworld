"""Normalized SEC evidence for the US tenant.

Raw EDGAR JSON and quarterly 13F archives are transport formats and are never persisted. These
tables retain compact, cited product facts: filing metadata, selected XBRL metrics, and a bounded
set of manager positions plus all-manager quarterly aggregates.
"""

from __future__ import annotations

import datetime as dt
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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class SecFiling(Base):
    __tablename__ = "sec_filings"
    __table_args__ = (
        Index("ix_sec_filings_symbol_date", "market", "code", "filing_date"),
        Index("ix_sec_filings_symbol_form", "market", "code", "form"),
    )

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True, index=True)
    accession_number: Mapped[str] = mapped_column(String(25), primary_key=True)
    cik: Mapped[int] = mapped_column(BigInteger, index=True)
    form: Mapped[str] = mapped_column(String(16), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    filing_date: Mapped[dt.date] = mapped_column(Date, index=True)
    report_date: Mapped[dt.date | None] = mapped_column(Date)
    accepted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    primary_document: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    items: Mapped[str | None] = mapped_column(Text)
    is_xbrl: Mapped[bool] = mapped_column(Boolean, default=False)
    is_inline_xbrl: Mapped[bool] = mapped_column(Boolean, default=False)
    filing_url: Mapped[str] = mapped_column(Text)
    source_updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class SecFinancialFact(Base):
    __tablename__ = "sec_financial_facts"
    __table_args__ = (
        UniqueConstraint(
            "market",
            "code",
            "metric",
            "period_end",
            "period_type",
            name="uq_sec_financial_fact_period",
        ),
        CheckConstraint(
            "period_type IN ('instant', 'quarter', 'annual')",
            name="ck_sec_financial_fact_period_type",
        ),
        Index("ix_sec_financial_facts_symbol_period", "market", "code", "period_end"),
        Index("ix_sec_financial_facts_metric_period", "market", "metric", "period_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[str] = mapped_column(String(8), index=True)
    code: Mapped[str] = mapped_column(String(16), index=True)
    metric: Mapped[str] = mapped_column(String(40), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(24))
    period_start: Mapped[dt.date | None] = mapped_column(Date)
    period_end: Mapped[dt.date] = mapped_column(Date)
    period_type: Mapped[str] = mapped_column(String(12))
    fiscal_year: Mapped[int | None] = mapped_column(Integer)
    fiscal_period: Mapped[str | None] = mapped_column(String(8))
    form: Mapped[str] = mapped_column(String(16))
    filed_at: Mapped[dt.date] = mapped_column(Date)
    accession_number: Mapped[str] = mapped_column(String(25))
    taxonomy: Mapped[str] = mapped_column(String(32))
    source_concept: Mapped[str] = mapped_column(String(128))
    frame: Mapped[str | None] = mapped_column(String(32))
    source_url: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SecurityIdentifier(Base):
    __tablename__ = "security_identifiers"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    identifier_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    identifier: Mapped[str] = mapped_column(String(32), primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(16), index=True)
    source: Mapped[str] = mapped_column(String(32))
    match_method: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float)
    verified_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class InstitutionalManager(Base):
    __tablename__ = "institutional_managers"

    cik: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    latest_report_date: Mapped[dt.date | None] = mapped_column(Date)
    latest_filing_date: Mapped[dt.date | None] = mapped_column(Date)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class InstitutionalPosition(Base):
    __tablename__ = "institutional_positions"
    __table_args__ = (
        CheckConstraint(
            "change_type IN ('new', 'increased', 'reduced', 'unchanged', 'exited')",
            name="ck_institutional_position_change_type",
        ),
        Index("ix_institutional_positions_symbol_period", "market", "code", "report_date"),
        Index("ix_institutional_positions_manager_period", "manager_cik", "report_date"),
    )

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    report_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    manager_cik: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("institutional_managers.cik"), primary_key=True
    )
    manager_name: Mapped[str] = mapped_column(Text)
    cusip: Mapped[str] = mapped_column(String(9))
    shares: Mapped[int] = mapped_column(BigInteger)
    value_usd: Mapped[float] = mapped_column(Float)
    prior_shares: Mapped[int | None] = mapped_column(BigInteger)
    share_change: Mapped[int | None] = mapped_column(BigInteger)
    change_pct: Mapped[float | None] = mapped_column(Float)
    change_type: Mapped[str] = mapped_column(String(12), index=True)
    filing_date: Mapped[dt.date] = mapped_column(Date)
    accession_number: Mapped[str] = mapped_column(String(25))
    source_url: Mapped[str] = mapped_column(Text)
    value_rank: Mapped[int] = mapped_column(Integer)


class InstitutionalHoldingSummary(Base):
    __tablename__ = "institutional_holding_summaries"
    __table_args__ = (
        Index(
            "ix_institutional_holding_summaries_symbol_period",
            "market",
            "code",
            "report_date",
        ),
    )

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    report_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    prior_report_date: Mapped[dt.date | None] = mapped_column(Date)
    latest_filing_date: Mapped[dt.date] = mapped_column(Date)
    managers_count: Mapped[int] = mapped_column(Integer)
    total_shares: Mapped[int] = mapped_column(BigInteger)
    total_value_usd: Mapped[float] = mapped_column(Float)
    new_positions: Mapped[int] = mapped_column(Integer)
    increased_positions: Mapped[int] = mapped_column(Integer)
    reduced_positions: Mapped[int] = mapped_column(Integer)
    exited_positions: Mapped[int] = mapped_column(Integer)
    unchanged_positions: Mapped[int] = mapped_column(Integer)
    net_share_change: Mapped[int | None] = mapped_column(BigInteger)
    net_change_pct: Mapped[float | None] = mapped_column(Float)
    # Null means the retained quarter pair is too sparse to rule out a split-like distortion.
    share_basis_comparable: Mapped[bool | None] = mapped_column(Boolean)
    source_url: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class RegulatoryDataState(Base):
    __tablename__ = "regulatory_data_state"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    as_of_date: Mapped[dt.date | None] = mapped_column(Date)
    last_success_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    records: Mapped[int] = mapped_column(Integer)
    symbols_covered: Mapped[int] = mapped_column(Integer)
    downloaded_bytes: Mapped[int] = mapped_column(BigInteger)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
