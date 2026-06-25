"""Ledger of agent signals already published — the dedupe + audit trail.

One row per (market, code, event_type, occurrence_key). The occurrence_key makes an event unique to
its instance (e.g. the date a 52-week high was set), so re-running detection never double-posts. Each
row links the feed post it produced.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class SignalEvent(Base):
    __tablename__ = "signal_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[str] = mapped_column(String(8), index=True)
    code: Mapped[str] = mapped_column(String(16), index=True)
    agent: Mapped[str] = mapped_column(String(48))  # the agent handle that fired it
    event_type: Mapped[str] = mapped_column(String(32))
    occurrence_key: Mapped[str] = mapped_column(String(48))  # unique per instance of the event
    post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id"), default=None)
    as_of_date: Mapped[dt.date | None] = mapped_column(default=None)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("market", "code", "event_type", "occurrence_key", name="uq_signal_event"),
    )
