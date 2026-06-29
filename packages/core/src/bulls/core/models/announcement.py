"""DSE news / price-sensitive announcements, classified + scored at onboarding.

We keep the important categories (dividend, earnings, rating, corporate actions, halts, PSI) and
drop pure noise (spot notices, trading-code changes, "no undisclosed info" clarifications). Each
kept row carries a `category` (controlled taxonomy) and a 0-100 `strength` (materiality), so agents
and the News tab can filter and rank cheaply. `key` is a content hash for idempotent upserts.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import Date, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[str] = mapped_column(String(8), index=True)
    code: Mapped[str] = mapped_column(String(16), index=True)
    published_at: Mapped[dt.date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(String(24), index=True)
    strength: Mapped[int] = mapped_column(Integer)  # 0-100 materiality
    headline: Mapped[str] = mapped_column(Text)
    # Full announcement text from DSE, and the language-neutral fields decoded from it (EPS now/prior,
    # dividend rate, record date, spot window, meeting agenda, …). The frontend renders the human
    # summary per-locale from `details`, so the decoding stays bilingual without storing prose.
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)  # content hash → idempotent upsert
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
