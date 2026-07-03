"""Block-market trades — negotiated large deals, one row per (market, code, trade date).

INTERNAL dataset (2026-07-03 decision): ingested and queryable via the admin API only; no public
surface until the sourcing question is settled (the per-scrip list comes from LankaBD, not the
exchange — see docs/redesign/2026-07-drops.md).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class BlockTrade(Base):
    __tablename__ = "block_trades"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    trade_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    quantity: Mapped[int] = mapped_column(BigInteger)  # shares crossed in the block window
    value_mn: Mapped[float] = mapped_column(Float)  # turnover, ৳ millions
    trades: Mapped[int] = mapped_column(Integer)  # number of negotiated deals
    max_price: Mapped[float | None] = mapped_column(Float)
    min_price: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
