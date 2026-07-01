"""Moderation audit log (docs/specs/feed-moderation.md §6).

Append-only: one row per decision the cascade makes about a post. Immutable by convention — we insert,
never update — so there is always a defensible trail of *which layer decided, why, and at what cost*
for a possible BSEC inquiry. `layer` is 0-4 (0=normalize .. 4=LLM); `model`/`tokens`/`cost` are only
set for the L4 (LLM) layer.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class ModerationEvent(Base):
    __tablename__ = "moderation_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    decision: Mapped[str] = mapped_column(String(10))  # Action value: allow|mask|label|hold|block
    layer: Mapped[int] = mapped_column(Integer)  # 0..4
    risk_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    categories: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)  # ["C1", ...]
    rule_ids: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(48), nullable=True)  # L4 only
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)  # L4 only
    cost: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)  # L4 only
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor: Mapped[str] = mapped_column(String(16), server_default="system")  # 'system' | 'reviewer'
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
