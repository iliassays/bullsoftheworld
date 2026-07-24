"""Daily archive of squeeze-taxonomy states (squeeze-monitor-v2).

One row per (market, code, family, session), upserted by the scan. Idempotent for identical
inputs, but not append-only: a re-scan after a methodology change rewrites that session in
place without retaining the prior version.

One row per (market, code, family, session). The scan task is the only writer; rows for closed
sessions are never rewritten, so "when was this first discovered" and "why did the
classification change" are answered by the archive itself, not by recomputation. Market data is
market-scoped (not tenant-scoped) like DailyBar/TickerAnalytics; tenant isolation happens at
the API layer, which only ever serves the requesting tenant's market.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import Date, DateTime, Float, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class SqueezeDailyState(Base):
    __tablename__ = "squeeze_daily_states"
    __table_args__ = (
        Index("ix_squeeze_daily_states_market_date", "market", "as_of_date"),
        Index("ix_squeeze_daily_states_market_code_family", "market", "code", "family"),
    )

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    family: Mapped[str] = mapped_column(String(40), primary_key=True)
    as_of_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    state: Mapped[str] = mapped_column(String(16))
    previous_state: Mapped[str | None] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(500))
    setup_price: Mapped[float | None] = mapped_column(Float)
    trigger_price: Mapped[float | None] = mapped_column(Float)
    invalidation_price: Mapped[float | None] = mapped_column(Float)
    risk_per_share: Mapped[float | None] = mapped_column(Float)
    planning_objective_price: Mapped[float | None] = mapped_column(Float)
    first_discovered_on: Mapped[dt.date] = mapped_column(Date)
    # Classification as it was known ON THIS SESSION. Reading these from the current
    # single-row TickerAnalytics made an archived screen mutate later and carry classification
    # the market did not yet have; they are therefore snapshotted per session.
    cap_tier: Mapped[str | None] = mapped_column(String(16))
    average_dollar_volume_mn: Mapped[float | None] = mapped_column(Float)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    methodology_version: Mapped[str] = mapped_column(String(48))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
