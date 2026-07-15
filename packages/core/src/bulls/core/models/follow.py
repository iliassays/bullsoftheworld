"""Follows — a user follows an account (e.g. an official desk). Keyed by (follower_id, followee_id).

Distinct from the watchlist (which tracks symbols): this tracks accounts. A user's Home shows posts
from the desks they follow plus activity on the companies they watch.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKeyConstraint, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class Follow(Base):
    __tablename__ = "follows"
    __table_args__ = (
        ForeignKeyConstraint(
            ["follower_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_follows_follower_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["followee_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_follows_followee_tenant",
            ondelete="CASCADE",
        ),
    )

    follower_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    followee_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
