"""Typed catalyst events shared within one branded market tenant.

A catalyst is a dated (or window-bounded) event that can change the evidence for a security:
record dates, AGMs/EGMs, board meetings, spot-market windows, and inferred periodic-report
windows. Events are derived deterministically from official sources already ingested by the
platform; confidence and timing kind are explicit so the UI can never present an inferred window
as a confirmed date. Post-event review fills `outcome` without rewriting how the event was known.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, Index, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base

EVENT_TYPES = (
    "record_date",
    "agm",
    "egm",
    "board_meeting",
    "spot_window",
    "periodic_report_window",
)
TIMING_KINDS = ("confirmed", "window")
CONFIDENCE_LEVELS = ("official_confirmed", "official_derived", "inferred_cadence")
EVENT_STATUSES = ("scheduled", "occurred", "cancelled")


class CatalystEvent(Base):
    __tablename__ = "research_catalyst_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('record_date', 'agm', 'egm', 'board_meeting', "
            "'spot_window', 'periodic_report_window')",
            name="ck_research_catalyst_event_type",
        ),
        CheckConstraint(
            "timing_kind IN ('confirmed', 'window')",
            name="ck_research_catalyst_timing_kind",
        ),
        CheckConstraint(
            "confidence IN ('official_confirmed', 'official_derived', 'inferred_cadence')",
            name="ck_research_catalyst_confidence",
        ),
        CheckConstraint(
            "status IN ('scheduled', 'occurred', 'cancelled')",
            name="ck_research_catalyst_status",
        ),
        CheckConstraint(
            "(timing_kind = 'confirmed' AND confirmed_date IS NOT NULL "
            "AND window_start IS NULL AND window_end IS NULL) OR "
            "(timing_kind = 'window' AND confirmed_date IS NULL "
            "AND window_start IS NOT NULL AND window_end IS NOT NULL "
            "AND window_start <= window_end)",
            name="ck_research_catalyst_timing_shape",
        ),
        CheckConstraint(
            "dedupe_key ~ '^[0-9a-f]{64}$'",
            name="ck_research_catalyst_dedupe_key",
        ),
        Index(
            "ix_research_catalyst_events_tenant_confirmed",
            "tenant_id",
            "market",
            "confirmed_date",
        ),
        Index(
            "ix_research_catalyst_events_tenant_window",
            "tenant_id",
            "market",
            "window_start",
        ),
        Index("ix_research_catalyst_events_security", "market", "code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(32))
    market: Mapped[str] = mapped_column(String(8))
    code: Mapped[str] = mapped_column(String(16))
    event_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(Text)
    timing_kind: Mapped[str] = mapped_column(String(12))
    confirmed_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    window_start: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    window_end: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="scheduled")
    confidence: Mapped[str] = mapped_column(String(24))
    source_type: Mapped[str] = mapped_column(String(32))
    source_ref: Mapped[str] = mapped_column(String(128))
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    known_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    expected_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
