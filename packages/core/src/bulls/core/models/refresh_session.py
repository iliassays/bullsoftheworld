"""Refresh sessions — the long-lived half of the fintech-standard token pair.

The access JWT stays short (30 min); this table backs the opaque, rotating refresh token that
keeps a user signed in for weeks. Only a SHA-256 hash of the token is stored — a database leak
alone can't mint sessions. `family` ties a rotation chain together: if a *replaced* token is
ever presented again (theft replay), the whole family is revoked at once.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    family: Mapped[str] = mapped_column(String(32), index=True)  # rotation chain id
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    replaced_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    user_agent: Mapped[str | None] = mapped_column(String(256), default=None)
    ip: Mapped[str | None] = mapped_column(String(64), default=None)
