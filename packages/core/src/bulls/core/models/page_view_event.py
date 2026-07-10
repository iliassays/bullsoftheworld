"""Append-only symbol page-view events — INTERNAL analytics only.

Page views are the noisiest, most gameable attention signal, so they are never surfaced as a
user-facing metric. They exist to (a) feed internal analytics and (b) be aggregated into
ticker_buzz_daily.unique_viewers_24h as a deweighted, optional input — never a standalone
"views rising" claim. A viewer is identified by user_id when logged in, else an anonymous
client-supplied session_hash; distinct viewers are counted at aggregation time.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class PageViewEvent(Base):
    __tablename__ = "page_view_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    market: Mapped[str] = mapped_column(String(8))
    code: Mapped[str] = mapped_column(String(16))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    session_hash: Mapped[str | None] = mapped_column(String(64), default=None)  # anon viewer id
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_page_view_tenant_market_code_created",
            "tenant_id",
            "market",
            "code",
            "created_at",
        ),
    )
