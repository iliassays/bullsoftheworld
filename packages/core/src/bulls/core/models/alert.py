"""Alerts — data events delivered to the users who watch or hold a stock.

AlertEvent is the per-user inbox row (fanned out at publish time, so reads are a plain indexed
scan — no join against watchlists on every bell poll). PriceAlert is a user-set level; the intraday
quote poll flips it to triggered exactly once and drops an AlertEvent alongside.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    market: Mapped[str] = mapped_column(String(8))
    code: Mapped[str | None] = mapped_column(String(16), default=None)  # None = market-wide
    kind: Mapped[str] = mapped_column(String(24))  # signal | price_cross | ownership | earnings
    # Bilingual like Post.body_i18n: rendered once at write time, served per reader locale.
    title_i18n: Mapped[dict] = mapped_column(JSON)
    body_i18n: Mapped[dict | None] = mapped_column(JSON, default=None)
    ref_post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id"), default=None)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (Index("ix_alert_events_user_created", "user_id", "created_at"),)


class PriceAlert(Base):
    __tablename__ = "price_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    market: Mapped[str] = mapped_column(String(8))
    code: Mapped[str] = mapped_column(String(16), index=True)
    level: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(6))  # above | below
    triggered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
