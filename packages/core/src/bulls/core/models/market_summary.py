"""Market-wide EOD aggregate: one row per (market, trading day).

Index levels (DSEX, DS30), turnover, trade/volume counts, and market cap — the backdrop a single
symbol's move is read against. Symbol-agnostic, so the same table serves every tenant's exchange.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, Date, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class MarketSummary(Base):
    __tablename__ = "market_summary"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    dsex: Mapped[float | None] = mapped_column(Float)
    dsex_change: Mapped[float | None] = mapped_column(Float)
    ds30: Mapped[float | None] = mapped_column(Float)
    ds30_change: Mapped[float | None] = mapped_column(Float)
    benchmark_code: Mapped[str | None] = mapped_column(String(16))
    benchmark_close: Mapped[float | None] = mapped_column(Float)
    benchmark_change: Mapped[float | None] = mapped_column(Float)
    total_trade: Mapped[int | None] = mapped_column(Integer)
    total_value_mn: Mapped[float | None] = mapped_column(Float)
    total_volume: Mapped[int | None] = mapped_column(
        BigInteger
    )  # market-wide daily volume nears int32
    total_market_cap_mn: Mapped[float | None] = mapped_column(Float)
