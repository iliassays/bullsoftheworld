"""Archive of the daily research shortlist — one row per slot per session.

Without this table the slate is recomputed live from ``ticker_analytics``, which holds a single
current row per symbol. That makes "what did you show me on Tuesday?" unanswerable and any
outcome tracking impossible, because the ranking inputs are overwritten every session.

``evidence_mode`` follows ``squeeze_daily_states``:

``forward``
    Written by the scan task on the session itself. This is the real record — what a reader
    actually saw on that date.
``reconstructed``
    Backfilled later from stored bars. Legitimate here in a way it is not for most replays,
    because all four ranking axes (move, relative volume, level proximity, range extremity) come
    from the bars themselves, so the *ranking* carries no look-ahead. Two caveats remain and are
    surfaced in the UI: only currently-listed symbols exist in the store, so a name that has since
    delisted can never appear in a reconstructed slate. Historical fundamentals are deliberately
    omitted because the point-in-time EPS/NAV publication state is not available in this archive.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, Date, DateTime, Float, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class DailyShortlistState(Base):
    """One shortlisted name as it was ranked on one session."""

    __tablename__ = "daily_shortlist_states"
    __table_args__ = (
        CheckConstraint(
            "evidence_mode IN ('forward', 'reconstructed')",
            name="ck_daily_shortlist_states_evidence_mode",
        ),
        CheckConstraint("rank >= 1", name="ck_daily_shortlist_states_rank"),
        CheckConstraint(
            "eligible_names >= 0 AND excluded_illiquid >= 0 AND excluded_short_history >= 0",
            name="ck_daily_shortlist_states_counts",
        ),
        Index("ix_daily_shortlist_states_market_date", "market", "as_of_date"),
    )

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    as_of_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    rank: Mapped[int] = mapped_column(Integer)
    attention_score: Mapped[float] = mapped_column(Float)
    # The close the row was ranked on — the reference every later outcome is measured against.
    close: Mapped[float] = mapped_column(Float)
    change_pct: Mapped[float | None] = mapped_column(Float)
    sector: Mapped[str | None] = mapped_column(String(64))
    pe: Mapped[float | None] = mapped_column(Float)
    # Structured facts/cautions preserve evidence values and allow language-specific rendering.
    # The methodology version records which ranking implementation produced those facts.
    facts: Mapped[list] = mapped_column(JSONB, default=list)
    cautions: Mapped[list] = mapped_column(JSONB, default=list)
    # How many names the slate was ranked from, for honest context on a thin session.
    eligible_names: Mapped[int] = mapped_column(Integer)
    excluded_illiquid: Mapped[int] = mapped_column(Integer)
    excluded_short_history: Mapped[int] = mapped_column(Integer)
    slate_size: Mapped[int] = mapped_column(Integer)
    notes: Mapped[list] = mapped_column(JSONB, default=list)
    base_rates: Mapped[dict] = mapped_column(JSONB, default=dict)
    evidence_mode: Mapped[str] = mapped_column(String(16), default="forward")
    methodology_version: Mapped[str] = mapped_column(String(48))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
