"""Shared publication schedules derived from market calendars and worker UTC jobs."""

from __future__ import annotations

import datetime as dt

from bulls.core.markets import get_market_profile


def _is_trading_day(date: dt.date, market: str) -> bool:
    profile = get_market_profile(market)
    return date.isoweekday() in profile.trading_isoweekdays and date not in profile.holidays


def analysis_ready_at(market: str, session_date: dt.date) -> dt.datetime:
    """UTC publication time for one completed market session."""

    profile = get_market_profile(market)
    close_local = dt.datetime.combine(
        session_date,
        profile.close_time_on(session_date),
        tzinfo=profile.tz,
    )
    close_utc = close_local.astimezone(dt.UTC)
    ready = dt.datetime.combine(close_utc.date(), profile.analytics_ready_utc, tzinfo=dt.UTC)
    if ready <= close_utc:
        ready += dt.timedelta(days=1)
    return ready


def analysis_schedule(now: dt.datetime, market: str) -> tuple[dt.date, dt.datetime]:
    """Expected published session and next scheduled analytics publication."""

    if now.tzinfo is None:
        raise ValueError("analysis schedule requires a timezone-aware datetime")
    profile = get_market_profile(market)
    local_date = now.astimezone(profile.tz).date()

    expected = local_date
    for _ in range(370):
        if _is_trading_day(expected, market) and analysis_ready_at(market, expected) <= now:
            break
        expected -= dt.timedelta(days=1)
    else:  # pragma: no cover - every supported market has regular trading days
        raise RuntimeError(f"Could not resolve expected analytics date for {market}")

    candidate = local_date
    for _ in range(370):
        if _is_trading_day(candidate, market):
            ready = analysis_ready_at(market, candidate)
            if ready > now:
                return expected, ready
        candidate += dt.timedelta(days=1)
    raise RuntimeError(f"Could not resolve next analytics publication for {market}")
