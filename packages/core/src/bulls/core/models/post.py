"""Post + Cashtag models.

Cashtags are parsed at write time and stored denormalized so symbol pages and trending are
cheap reads. `sentiment` is set by the user or auto-tagged later by the AI worker (step 4).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_posts_id_tenant"),
        CheckConstraint(
            "sentiment IS NULL OR sentiment IN ('bull', 'bear')", name="ck_posts_sentiment"
        ),
        CheckConstraint("kind IN ('user', 'note')", name="ck_posts_kind"),
        CheckConstraint(
            "moderation_status IN ('published', 'pending', 'held', 'blocked', 'deleted')",
            name="ck_posts_moderation_status",
        ),
    )

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
    # Optional image (agent-generated cards only, e.g. the Evening Wrap). Never user uploads.
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(8), server_default="user")  # 'user' | 'note' (agent)
    # Feed moderation (see docs/specs/feed-moderation.md). Default 'published' so the fast path and
    # agent notes are unaffected; the write-path gate sets 'pending'/'blocked' when a post is caught.
    # Feed reads must filter to 'published'. 'held' = a reviewer parked it; 'blocked' = rejected.
    moderation_status: Mapped[str] = mapped_column(
        String(10), server_default="published", index=True
    )  # 'published' | 'pending' | 'held' | 'blocked' | 'deleted'
    moderation_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Hash of the L0-normalized body — repost/duplicate detection + de-dupe of blocked text.
    normalized_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
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
    __table_args__ = (
        CheckConstraint("kind IN ('agree', 'disagree')", name="ck_post_reactions_kind"),
        ForeignKeyConstraint(
            ["user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_post_reactions_user_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["post_id", "tenant_id"],
            ["posts.id", "posts.tenant_id"],
            name="fk_post_reactions_post_tenant",
            ondelete="CASCADE",
        ),
    )

    post_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(8))  # 'agree' | 'disagree'
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
