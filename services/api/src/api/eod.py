"""Helpers for keeping interpreted analytics on one completed-session clock."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from bulls.core.models import DailyBar


def completed_session_change_pct(closes_desc: list[float]) -> float | None:
    """Return the latest raw-close change from closes ordered newest first."""
    if len(closes_desc) < 2 or closes_desc[1] <= 0:
        return None
    return (closes_desc[0] / closes_desc[1] - 1) * 100


async def latest_completed_session_change_pct(
    session, market: str, code: str, as_of: dt.date
) -> float | None:
    """Load the two raw closes ending at ``as_of`` and calculate their session change.

    Raw closes intentionally match the exchange's observed session move. Adjusted closes are useful
    for long-horizon returns, but can rewrite the latest one-day move after a corporate action.
    """
    closes = list(
        await session.scalars(
            select(DailyBar.close)
            .where(
                DailyBar.market == market,
                DailyBar.code == code,
                DailyBar.date <= as_of,
            )
            .order_by(DailyBar.date.desc())
            .limit(2)
        )
    )
    return completed_session_change_pct(closes)
