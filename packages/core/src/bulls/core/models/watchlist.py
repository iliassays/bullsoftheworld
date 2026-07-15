"""Watchlist — symbols a user tracks. Keyed by (user_id, market, code)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKeyConstraint, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_watchlist_items_user_tenant",
            ondelete="CASCADE",
        ),
    )

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
