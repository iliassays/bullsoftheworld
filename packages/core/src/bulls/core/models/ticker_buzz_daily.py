"""Daily social-attention snapshot — one row per symbol per day, written after the EOD close.

Mirrors the TickerAnalytics snapshot pattern so attention *trends* are cheap and reliable to read.
Storing watchers_total as a daily snapshot (rather than deriving it live) keeps the watcher trend
correct even though watchlist removals delete the underlying row. Descriptive counts only.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class TickerBuzzDaily(Base):
    __tablename__ = "ticker_buzz_daily"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)

    posts_24h: Mapped[int] = mapped_column(Integer, default=0)
    reactions_24h: Mapped[int] = mapped_column(Integer, default=0)
    replies_24h: Mapped[int] = mapped_column(Integer, default=0)
    watchers_total: Mapped[int] = mapped_column(Integer, default=0)  # cumulative → trend source
    unique_viewers_24h: Mapped[int | None] = mapped_column(Integer, default=None)  # Phase D

    computed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
