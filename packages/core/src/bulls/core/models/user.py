"""User model. `tenant_id` gives row-level tenant isolation (MVP)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    handle: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    # Nullable: existing accounts + agent users have no email. Stored lowercased; unique when present.
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, default=None)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Phone (BD, normalized +8801XXXXXXXXX). Unique when present. OTP verification is a later phase.
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True, default=None)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    password_hash: Mapped[str] = mapped_column(String(255))
    locale: Mapped[str] = mapped_column(String(8), default="bn")
    # Official verified account — an automated desk (or a vetted analyst). Drives the verified badge
    # and the desk profile; independent of the handle so renames don't affect detection.
    is_official: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Access role. 'user' = normal member (default for every signup); 'admin' = ops/moderation
    # (can delete any post or comment). Independent of is_official (the verified-desk badge).
    role: Mapped[str] = mapped_column(String(16), default="user", server_default="user", index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
