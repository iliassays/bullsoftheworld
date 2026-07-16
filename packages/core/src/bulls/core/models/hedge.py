"""Persisted read models for the private Hedge research application.

Historical simulation is batch work.  The web process reads these tables only; a separate,
resource-limited refresh job replaces the latest snapshot after EOD data is complete.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, DateTime, Float, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class HedgeTrackRecordSnapshot(Base):
    __tablename__ = "hedge_track_record_snapshots"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    strategy: Mapped[str] = mapped_column(String(32), primary_key=True)
    as_of_date: Mapped[dt.date] = mapped_column(Date)
    payload: Mapped[dict] = mapped_column(JSONB)
    computed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class HedgeDailyScanSnapshot(Base):
    """One immutable, point-in-time Quality Reversal monitor publication per market session."""

    __tablename__ = "hedge_daily_scan_snapshots"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    strategy: Mapped[str] = mapped_column(String(32), primary_key=True)
    as_of_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(String(64))
    computed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class HedgeSignal(Base):
    __tablename__ = "hedge_signals"
    __table_args__ = (
        Index(
            "ix_hedge_signals_scope_status_date",
            "tenant_id",
            "market",
            "strategy",
            "status",
            "signal_date",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    strategy: Mapped[str] = mapped_column(String(32), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    signal_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    entry: Mapped[float] = mapped_column(Float)
    stop: Mapped[float] = mapped_column(Float)
    target: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(12))
    exit_date: Mapped[dt.date | None] = mapped_column(Date)
    exit_px: Mapped[float | None] = mapped_column(Float)
    result_pct: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
