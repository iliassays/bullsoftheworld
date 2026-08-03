"""Company reference data scraped from the exchange's company page.

CompanyProfile is slow-moving structure + fundamentals (one row per symbol, overwritten on refresh).
ShareholdingSnapshot is the ownership breakdown per disclosure date — a time series we diff later.
Both carry `market` so the same tables serve every tenant's exchange.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    sector: Mapped[str | None] = mapped_column(String(64))
    market_category: Mapped[str | None] = mapped_column(String(4))
    instrument_type: Mapped[str | None] = mapped_column(String(32))
    listing_year: Mapped[int | None] = mapped_column(Integer)
    face_value: Mapped[float | None] = mapped_column(Float)
    market_lot: Mapped[int | None] = mapped_column(Integer)
    authorized_capital_mn: Mapped[float | None] = mapped_column(Float)
    paid_up_capital_mn: Mapped[float | None] = mapped_column(Float)
    outstanding_shares: Mapped[int | None] = mapped_column(
        BigInteger
    )  # telcos exceed int32 (>2.1B)
    market_cap_mn: Mapped[float | None] = mapped_column(Float)
    free_float_mcap_mn: Mapped[float | None] = mapped_column(Float)
    year_end: Mapped[str | None] = mapped_column(String(16))
    latest_dividend: Mapped[str | None] = mapped_column(String(128))
    cash_dividend_pct: Mapped[float | None] = mapped_column(Float)
    eps: Mapped[float | None] = mapped_column(Float)
    nav_per_share: Mapped[float | None] = mapped_column(Float)
    short_term_loan_mn: Mapped[float | None] = mapped_column(Float)
    long_term_loan_mn: Mapped[float | None] = mapped_column(Float)
    reserve_surplus_mn: Mapped[float | None] = mapped_column(Float)
    oci_mn: Mapped[float | None] = mapped_column(Float)
    credit_rating_long: Mapped[str | None] = mapped_column(String(48))
    credit_rating_short: Mapped[str | None] = mapped_column(String(48))
    operational_status: Mapped[str | None] = mapped_column(String(32))
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class AnnualFinancial(Base):
    """Per-fiscal-year EPS / NAV / profit — the series behind earnings-growth screens."""

    __tablename__ = "company_financials"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, primary_key=True)
    eps: Mapped[float | None] = mapped_column(Float)
    nav_per_share: Mapped[float | None] = mapped_column(Float)
    profit_mn: Mapped[float | None] = mapped_column(Float)


class DividendRecord(Base):
    """Per-year cash + stock dividend — the series behind dividend-consistency screens."""

    __tablename__ = "company_dividends"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    cash_pct: Mapped[float | None] = mapped_column(Float)
    # DSE discloses cash as a percentage of face value; US XBRL reports currency per share.
    cash_per_share: Mapped[float | None] = mapped_column(Float)
    bonus_pct: Mapped[float | None] = mapped_column(Float)


class SectorPE(Base):
    """Sector-wide median P/E (one row per sector) for relative valuation."""

    __tablename__ = "sector_pe"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    sector: Mapped[str] = mapped_column(String(64), primary_key=True)
    median_pe: Mapped[float | None] = mapped_column(Float)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class ShareholdingSnapshot(Base):
    __tablename__ = "shareholding_snapshots"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    as_of_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    # DSE identifies the reporting period but not a reliable publication timestamp. Preserve when
    # Atlas first observed the row so historical research cannot use it before it was knowable.
    first_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    sponsor_director: Mapped[float | None] = mapped_column(Float)
    govt: Mapped[float | None] = mapped_column(Float)
    institute: Mapped[float | None] = mapped_column(Float)
    foreign_pct: Mapped[float | None] = mapped_column(Float)  # 'foreign' is a SQL reserved word
    public: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        CheckConstraint(
            "sponsor_director is not null and institute is not null and "
            "foreign_pct is not null and public is not null and "
            "sponsor_director between 0 and 100 and "
            "coalesce(govt, 0) between 0 and 100 and "
            "institute between 0 and 100 and foreign_pct between 0 and 100 and "
            "public between 0 and 100",
            name="ck_shareholding_category_percentages",
        ),
        CheckConstraint(
            "sponsor_director + coalesce(govt, 0) + institute + foreign_pct + public "
            "between 99 and 101",
            name="ck_shareholding_composition_total",
        ),
    )
