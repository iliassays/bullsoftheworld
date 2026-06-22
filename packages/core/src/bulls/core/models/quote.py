"""Persisted market data: latest snapshot per symbol + historical daily bars.

QuoteSnapshot is the newest delayed quote (overwritten each poll). DailyBar is the EOD history.
Both carry `market` so the same tables serve every tenant's exchange.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class QuoteSnapshot(Base):
    __tablename__ = "quote_snapshots"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    ltp: Mapped[float] = mapped_column(Float)
    change: Mapped[float] = mapped_column(Float)
    change_pct: Mapped[float] = mapped_column(Float)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    prev_close: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)
    trades: Mapped[int] = mapped_column(Integer)
    as_of: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    is_delayed: Mapped[bool] = mapped_column(Boolean, default=True)


class DailyBar(Base):
    __tablename__ = "daily_bars"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)
