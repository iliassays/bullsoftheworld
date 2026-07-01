"""Follows — a user follows an account (e.g. an official desk). Keyed by (follower_id, followee_id).

Distinct from the watchlist (which tracks symbols): this tracks accounts. A user's Home shows posts
from the desks they follow plus activity on the companies they watch.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class Follow(Base):
    __tablename__ = "follows"

    follower_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    followee_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True, index=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
