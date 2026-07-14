"""Daily short-sale volume per symbol, from FINRA's Reg SHO consolidated NMS files.

One row per (market, code, session date). `(short_volume + short_exempt_volume) / total_volume` is
the short-sale share of volume reported to FINRA facilities — not whole-market volume and NOT short interest. It includes
market-maker liquidity provision, so the UI/agents must never frame it as "bearish bets". FINRA publishes the file each evening
(~18:00 ET); ingestion is idempotent per day and quietly skips days FINRA hasn't published.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import Date, DateTime, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class ShortVolumeDaily(Base):
    __tablename__ = "short_volume_daily"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    # FINRA can report fractional shares for odd-lot activity. Keep source precision so valid
    # sub-share rows are not discarded and the published record count remains auditable.
    short_volume: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    short_exempt_volume: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    total_volume: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="finra_cnms")
    fetched_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # The daily agent scans one session across the whole market.
        Index("ix_short_volume_daily_market_date", "market", "date"),
    )
