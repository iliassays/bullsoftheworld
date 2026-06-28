"""Post + Cashtag models.

Cashtags are parsed at write time and stored denormalized so symbol pages and trending are
cheap reads. `sentiment` is set by the user or auto-tagged later by the AI worker (step 4).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    # Agent desk-notes come from deterministic bilingual templates, so we store BOTH renders
    # ({"en": ..., "bn": ...}) and the feed serves whichever matches the reader's language flag.
    # Null for user-written posts (shown as typed, in whatever language the author used).
    body_i18n: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(8))  # 'bull' | 'bear' | None
    kind: Mapped[str] = mapped_column(String(8), server_default="user")  # 'user' | 'note' (agent)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Cashtag(Base):
    __tablename__ = "cashtags"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    market: Mapped[str] = mapped_column(String(8), index=True)
    code: Mapped[str] = mapped_column(String(16), index=True)


class PostReaction(Base):
    """One reaction per user per post — conviction on the post's take, not a vanity 'like'.

    Composite PK (post_id, user_id) enforces uniqueness; switching stance is an upsert of `kind`.
    """

    __tablename__ = "post_reactions"

    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(8))  # 'agree' | 'disagree'
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
