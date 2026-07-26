"""Daily archive of versioned squeeze-taxonomy states.

One row exists per (market, code, family, session). The live scan is the authoritative writer;
once it records a session, that forward row is immutable. A live scan may replace a reconstructed
placeholder for the same key, but replay can never overwrite or extend a live timeline. This lets
the archive answer when a setup was discovered and why it changed without hindsight relabelling.

Market data is market-scoped (not tenant-scoped) like DailyBar/TickerAnalytics; tenant isolation
happens at the API layer, which only ever serves the requesting tenant's market.
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
    # "forward"      — written by the nightly scan on the session it describes.
    # "reconstructed" — computed later from stored bars. Reconstructions inherit the store's
    # survivorship (delisted names are simply absent) and cannot see inputs that were never
    # recorded historically, so they may never be quoted as forward performance.
    evidence_mode: Mapped[str] = mapped_column(
        String(16), default="forward", server_default="forward"
    )
    average_dollar_volume_mn: Mapped[float | None] = mapped_column(Float)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    methodology_version: Mapped[str] = mapped_column(String(48))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
