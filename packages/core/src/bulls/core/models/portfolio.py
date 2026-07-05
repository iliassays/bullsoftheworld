"""Portfolio — manual holdings the user typed in. Never linked to a broker account.

One row per (user, market, code): quantity + average buy price. Valuation happens at read time
against the latest QuoteSnapshot, so this table stores only what the user told us.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer)
    avg_cost: Mapped[float] = mapped_column(Float)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PortfolioSnapshot(Base):
    """One row per (user, market, day) — the total value/cost of everything they held that day,
    taken once at EOD. We only snapshot the AGGREGATE, never reconstruct one: a holding's quantity
    or avg_cost can change at any time (add/edit/delete), so projecting today's holdings backward
    across historical prices would show a fictional 'what if you always held this' line, not what
    the user actually experienced. Growth history starts the day we start snapshotting — no backfill.
    """

    __tablename__ = "portfolio_snapshots"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    total_value: Mapped[float | None] = mapped_column(Float)  # None if nothing could be priced
    total_cost: Mapped[float] = mapped_column(Float)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
