"""FINRA bi-monthly consolidated short interest — the authoritative open short position.

This is the *stock* of open short positions at a settlement date, and is categorically different
from `ShortVolumeDaily`, which is a daily *flow* of short-marked executions (and includes
market-maker liquidity provision). Only this table can support "short interest", "% of shares
outstanding/float" or "days to cover" language; daily short volume never can.

Point-in-time contract
----------------------
FINRA reports a settlement date but the record is not public until its dissemination date. Using
`settlement_date` as the knowledge date would leak roughly a week of hindsight into every
backtest, so research MUST filter on `known_at`:

* `known_at` is a deterministic, conservative model — settlement + `DISSEMINATION_BUSINESS_DAYS`
  US trading days — so a backfill and a live run agree exactly and are reproducible.
* `first_observed_at` records when our ingestion actually saw the row. It is audit evidence, not
  the research gate: for backfilled history it is simply "now" and proves nothing about
  publication.

Observed behaviour on 2026-07-25: the 2026-07-15 settlement was already retrievable (~7 trading
days), so the 8-day model sits at or after real publication — conservative in the safe direction.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import Date, DateTime, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base

# FINRA's standard dissemination is the 8th business day after the reporting settlement date.
# Raising this is always safe; lowering it re-dates history and is a methodology change.
DISSEMINATION_BUSINESS_DAYS = 8


class ShortInterestBiweekly(Base):
    __tablename__ = "short_interest_biweekly"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    settlement_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)

    # The research gate. Never filter point-in-time work on settlement_date.
    known_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_observed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    shares_short: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    previous_shares_short: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    # FINRA's own average daily volume and days-to-cover, recorded rather than recomputed so the
    # published figure and ours cannot disagree. FINRA derives days_to_cover over its own volume
    # window; it is not shares_short / our avg_volume_20.
    average_daily_volume: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    days_to_cover: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    change_pct: Mapped[float | None] = mapped_column(Numeric(14, 4))
    market_class: Mapped[str | None] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="finra_consolidated")

    __table_args__ = (
        # Research reads "latest row known on date D for these codes".
        Index("ix_short_interest_market_known", "market", "known_at"),
        Index("ix_short_interest_market_code_known", "market", "code", "known_at"),
    )
