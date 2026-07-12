"""Bound raw growth analytics while preserving aggregate business metrics."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import delete

from bulls.core.db import get_sessionmaker
from bulls.core.models import BetaFeedback, PageViewEvent, ProductEvent

RAW_EVENT_RETENTION_DAYS = 180
BETA_FEEDBACK_RETENTION_DAYS = 365


async def prune_raw_events(now: dt.datetime | None = None) -> dict[str, int]:
    cutoff = (now or dt.datetime.now(dt.UTC)) - dt.timedelta(days=RAW_EVENT_RETENTION_DAYS)
    async with get_sessionmaker()() as session:
        product = await session.execute(
            delete(ProductEvent).where(ProductEvent.created_at < cutoff)
        )
        views = await session.execute(
            delete(PageViewEvent).where(PageViewEvent.created_at < cutoff)
        )
        feedback_cutoff = (now or dt.datetime.now(dt.UTC)) - dt.timedelta(
            days=BETA_FEEDBACK_RETENTION_DAYS
        )
        feedback = await session.execute(
            delete(BetaFeedback).where(BetaFeedback.created_at < feedback_cutoff)
        )
        await session.commit()
    return {
        "product_events": product.rowcount or 0,
        "page_view_events": views.rowcount or 0,
        "beta_feedback": feedback.rowcount or 0,
    }
