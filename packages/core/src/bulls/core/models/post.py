"""Post + Cashtag models.

Cashtags are parsed at write time and stored denormalized so symbol pages and trending are
cheap reads. `sentiment` is set by the user or auto-tagged later by the AI worker (step 4).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    sentiment: Mapped[str | None] = mapped_column(String(8))  # 'bull' | 'bear' | None
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Cashtag(Base):
    __tablename__ = "cashtags"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    market: Mapped[str] = mapped_column(String(8), index=True)
    code: Mapped[str] = mapped_column(String(16), index=True)
