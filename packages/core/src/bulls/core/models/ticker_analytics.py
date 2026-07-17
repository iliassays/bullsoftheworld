"""Persisted technical-analysis snapshot — one row per symbol, refreshed each EOD.

Computing the analytics engine over every symbol on each dashboard load would be far too slow, so
the ingestion scheduler computes it once after the close and upserts here. The screener then reads
this table with plain SQL filters (RSI <= 30, close near support, CMF > 0, ...). Descriptive facts
only — nothing here is a recommendation.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, Date, DateTime, Float, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class TickerAnalytics(Base):
    __tablename__ = "ticker_analytics"
    __table_args__ = (Index("ix_ticker_analytics_market_cap_tier", "market", "cap_tier"),)

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    as_of_date: Mapped[dt.date] = mapped_column(Date)
    last_close: Mapped[float] = mapped_column(Float)

    # Trend
    sma_50: Mapped[float | None] = mapped_column(Float)
    sma_200: Mapped[float | None] = mapped_column(Float)
    above_sma_50: Mapped[bool | None] = mapped_column(Boolean)
    above_sma_200: Mapped[bool | None] = mapped_column(Boolean)

    # Momentum / volatility
    rsi_14: Mapped[float | None] = mapped_column(Float)
    atr_14: Mapped[float | None] = mapped_column(Float)
    mom_3_1: Mapped[float | None] = mapped_column(Float)  # 3-1 month price momentum, %
    mom_6_1: Mapped[float | None] = mapped_column(Float)  # 6-1 month price momentum, %
    mom_12_1: Mapped[float | None] = mapped_column(Float)  # 12-1 month price momentum, %
    volatility: Mapped[float | None] = mapped_column(Float)  # annualised daily-return vol, %

    # Structure
    nearest_support: Mapped[float | None] = mapped_column(Float)
    nearest_resistance: Mapped[float | None] = mapped_column(Float)
    week52_high: Mapped[float | None] = mapped_column(Float)
    week52_low: Mapped[float | None] = mapped_column(Float)
    pct_from_52w_high: Mapped[float | None] = mapped_column(Float)
    pct_from_52w_low: Mapped[float | None] = mapped_column(Float)

    # Volume
    avg_volume_20: Mapped[float | None] = mapped_column(Float)
    relative_volume: Mapped[float | None] = mapped_column(Float)  # today vs 20-day avg
    rel_volume_5d: Mapped[float | None] = mapped_column(Float)  # 5-day avg vs 60-day avg
    rel_volume_1m: Mapped[float | None] = mapped_column(Float)  # 22-day avg vs 60-day avg
    cmf_20: Mapped[float | None] = mapped_column(Float)  # >0 accumulation, <0 distribution
    obv_slope: Mapped[float | None] = mapped_column(
        Float
    )  # OBV trend (vol-leads-price): >0 = accum

    # Valuation — derived daily from last_close x fundamentals (weekly company scrape)
    market_cap_mn: Mapped[float | None] = mapped_column(Float)
    # Canonical size tier (bulls.core.markets.cap_tier): mega|large|mid|small|micro, or NULL when
    # market_cap_mn is unknown — presented as "unclassified", never guessed. Denormalized here so
    # the screener and browse pages filter in SQL without restating thresholds.
    cap_tier: Mapped[str | None] = mapped_column(String(16))
    free_float_cap_mn: Mapped[float | None] = mapped_column(Float)
    pe_ratio: Mapped[float | None] = mapped_column(Float)  # None when EPS <= 0
    pb_ratio: Mapped[float | None] = mapped_column(Float)
    dividend_yield: Mapped[float | None] = mapped_column(Float)  # %
    roe: Mapped[float | None] = mapped_column(Float)  # % — return on equity (EPS / NAV per share)
    pe_vs_sector: Mapped[float | None] = mapped_column(
        Float
    )  # pe_ratio / sector median (<1 = cheap)
    eps_growth_yoy: Mapped[float | None] = mapped_column(Float)  # % latest vs prior fiscal year

    # Ownership — latest shareholding % + month-over-month change (surfaced from the snapshot series)
    sponsor_pct: Mapped[float | None] = mapped_column(Float)
    institute_pct: Mapped[float | None] = mapped_column(Float)
    foreign_pct: Mapped[float | None] = mapped_column(Float)
    public_pct: Mapped[float | None] = mapped_column(Float)
    institute_delta: Mapped[float | None] = mapped_column(Float)  # vs prior snapshot
    foreign_delta: Mapped[float | None] = mapped_column(Float)

    computed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    methodology_version: Mapped[str | None] = mapped_column(String(48))
    input_fingerprint: Mapped[str | None] = mapped_column(String(64))
    point_in_time_complete: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
