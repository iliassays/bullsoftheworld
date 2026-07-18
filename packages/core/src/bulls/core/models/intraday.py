"""Durable delayed-intraday research observations and sampled bars.

The DSE public quote page exposes cumulative delayed snapshots, not a trade tape. Atlas therefore
retains the immutable observations and labels the derived 15-minute rows as sampled bars. Nothing
in this schema represents those rows as exchange-native OHLC bars or as real-time data.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class IntradayQuoteObservation(Base):
    """One immutable provider snapshot for one security at one knowledge time."""

    __tablename__ = "intraday_quote_observations"
    __table_args__ = (
        CheckConstraint("ltp > 0", name="ck_intraday_quote_observations_ltp"),
        CheckConstraint("high > 0 AND low > 0", name="ck_intraday_quote_observations_range"),
        CheckConstraint("high >= low", name="ck_intraday_quote_observations_range_order"),
        CheckConstraint(
            "volume >= 0 AND trades >= 0", name="ck_intraday_quote_observations_counts"
        ),
        CheckConstraint(
            "sequence_status IN ('baseline', 'advanced', 'unchanged', 'regressed')",
            name="ck_intraday_quote_observations_sequence",
        ),
        CheckConstraint(
            "time_quality IN ('source_timestamp', 'ingestion_upper_bound')",
            name="ck_intraday_quote_observations_time_quality",
        ),
        Index(
            "ix_intraday_quote_observations_symbol_time",
            "market",
            "code",
            "observed_at",
        ),
        {"postgresql_partition_by": "RANGE (session_date)"},
    )

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    session_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    observed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_source_snapshots.id", ondelete="RESTRICT")
    )
    capture_slot: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    ltp: Mapped[float] = mapped_column(Float)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    prev_close: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(BigInteger)
    trades: Mapped[int] = mapped_column(Integer)
    turnover_mn: Mapped[float | None] = mapped_column(Float)
    session_vwap: Mapped[float | None] = mapped_column(Float)
    is_delayed: Mapped[bool] = mapped_column(Boolean)
    sequence_status: Mapped[str] = mapped_column(String(16))
    time_quality: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(48))
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IntradayBar(Base):
    """A sampled 15-minute capture bucket derived only from retained observations."""

    __tablename__ = "intraday_bars"
    __table_args__ = (
        CheckConstraint(
            "open > 0 AND high > 0 AND low > 0 AND close > 0", name="ck_intraday_bars_ohlc"
        ),
        CheckConstraint("high >= open AND high >= close", name="ck_intraday_bars_high"),
        CheckConstraint("low <= open AND low <= close", name="ck_intraday_bars_low"),
        CheckConstraint("interval_minutes > 0", name="ck_intraday_bars_interval"),
        CheckConstraint("observation_count > 0", name="ck_intraday_bars_observations"),
        CheckConstraint(
            "volume_delta IS NULL OR volume_delta >= 0",
            name="ck_intraday_bars_volume_delta",
        ),
        CheckConstraint(
            "trades_delta IS NULL OR trades_delta >= 0",
            name="ck_intraday_bars_trades_delta",
        ),
        CheckConstraint(
            "turnover_delta_mn IS NULL OR turnover_delta_mn >= 0",
            name="ck_intraday_bars_turnover_delta",
        ),
        CheckConstraint(
            "data_quality IN ('baseline', 'complete_delta', 'missing_turnover', 'counter_regression')",
            name="ck_intraday_bars_quality",
        ),
        CheckConstraint(
            "time_quality IN ('source_timestamp', 'ingestion_upper_bound')",
            name="ck_intraday_bars_time_quality",
        ),
        Index("ix_intraday_bars_symbol_time", "market", "code", "interval_start"),
        {"postgresql_partition_by": "RANGE (session_date)"},
    )

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    session_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    interval_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=15, server_default="15")
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume_delta: Mapped[int | None] = mapped_column(BigInteger)
    trades_delta: Mapped[int | None] = mapped_column(Integer)
    turnover_delta_mn: Mapped[float | None] = mapped_column(Float)
    interval_vwap: Mapped[float | None] = mapped_column(Float)
    cumulative_volume: Mapped[int] = mapped_column(BigInteger)
    cumulative_trades: Mapped[int] = mapped_column(Integer)
    cumulative_turnover_mn: Mapped[float | None] = mapped_column(Float)
    session_vwap: Mapped[float | None] = mapped_column(Float)
    observation_count: Mapped[int] = mapped_column(Integer)
    data_quality: Mapped[str] = mapped_column(String(24))
    time_quality: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(48))
    last_source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_source_snapshots.id", ondelete="RESTRICT")
    )
    known_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IntradayCaptureSession(Base):
    """Per-session completeness and freshness controls for intraday research admission."""

    __tablename__ = "intraday_capture_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('collecting', 'complete', 'incomplete')",
            name="ck_intraday_capture_sessions_status",
        ),
        CheckConstraint(
            "expected_slot_count > 0 AND observed_slot_count >= 0",
            name="ck_intraday_capture_sessions_slots",
        ),
        CheckConstraint(
            "expected_symbol_count >= 0 AND observed_symbol_count >= 0",
            name="ck_intraday_capture_sessions_symbols",
        ),
        CheckConstraint(
            "slot_completeness_pct >= 0 AND slot_completeness_pct <= 100",
            name="ck_intraday_capture_sessions_slot_pct",
        ),
        CheckConstraint(
            "symbol_completeness_pct >= 0 AND symbol_completeness_pct <= 100",
            name="ck_intraday_capture_sessions_symbol_pct",
        ),
        CheckConstraint(
            "vwap_coverage_pct >= 0 AND vwap_coverage_pct <= 100",
            name="ck_intraday_capture_sessions_vwap_pct",
        ),
        Index("ix_intraday_capture_sessions_market_status", "market", "status", "session_date"),
    )

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    session_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    expected_slot_count: Mapped[int] = mapped_column(Integer)
    observed_slot_count: Mapped[int] = mapped_column(Integer)
    expected_symbol_count: Mapped[int] = mapped_column(Integer)
    observed_symbol_count: Mapped[int] = mapped_column(Integer)
    observation_count: Mapped[int] = mapped_column(BigInteger)
    bar_count: Mapped[int] = mapped_column(BigInteger)
    vwap_bar_count: Mapped[int] = mapped_column(BigInteger)
    counter_regression_count: Mapped[int] = mapped_column(BigInteger)
    slot_completeness_pct: Mapped[float] = mapped_column(Float)
    symbol_completeness_pct: Mapped[float] = mapped_column(Float)
    vwap_coverage_pct: Mapped[float] = mapped_column(Float)
    first_observed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    latest_observed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    maximum_capture_lag_seconds: Mapped[float] = mapped_column(Float)
    research_eligible: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    blockers: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
