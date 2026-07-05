"""Daily chart-pattern detection result — one row per code, replaced nightly.

Precomputed by the same ingestion loop that fills `ticker_analytics` (`compute_all()`), reusing
bars it already fetched — see `bulls.analytics.patterns.detect_patterns`. `payload` holds the
structured pivots/trendlines/key-levels the frontend needs to actually draw the shape; the
screener reads the flat columns for the Ideas-board row text. Descriptive only — this is "what
shape the price history currently forms," never a recommendation. Evidence tier is `framework`
(classic technical analysis, not proven to have an edge on DSE) everywhere this is surfaced.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import Date, DateTime, Float, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class TickerPattern(Base):
    __tablename__ = "ticker_patterns"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    as_of_date: Mapped[dt.date] = mapped_column(Date, index=True)
    pattern_type: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24))
    start_date: Mapped[dt.date] = mapped_column(Date)
    end_date: Mapped[dt.date] = mapped_column(Date)
    breakout_date: Mapped[dt.date | None] = mapped_column(Date)
    strength_score: Mapped[float] = mapped_column(Float)
    # Everything CandleChart needs to draw the shape: pivots, resistance_line, support_line,
    # key_levels, touches_resistance, touches_support — the PatternMatch fields not promoted to
    # their own column, since only the screener's flat columns need to be SQL-filterable/sortable.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    computed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
