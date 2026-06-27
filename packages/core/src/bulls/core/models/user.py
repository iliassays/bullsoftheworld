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
    password_hash: Mapped[str] = mapped_column(String(255))
    locale: Mapped[str] = mapped_column(String(8), default="bn")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
