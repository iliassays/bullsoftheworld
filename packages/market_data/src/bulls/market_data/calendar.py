"""Market trading calendar - pure, timezone-correct helpers.

DSE remains the default for backward compatibility. New markets should call these helpers with a
``market=`` argument so trading days, hours, holidays, and timezone come from the shared market
profile rather than Dhaka constants.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from zoneinfo import ZoneInfo

from bulls.core.markets import get_market_profile

DHAKA = ZoneInfo("Asia/Dhaka")
MARKET_OPEN = dt.time(10, 0)
MARKET_CLOSE = dt.time(14, 30)
MARKET_HOLIDAYS: frozenset[dt.date] = get_market_profile("DSE").holidays


class Session(StrEnum):
    PRE_OPEN = "pre_open"  # trading day, before open
    OPEN = "open"  # within market hours
    POST_CLOSE = "post_close"  # trading day, after close
    WEEKEND = "weekend"  # non-trading day


def _profile_for(market: str | None):
    return get_market_profile(market or "DSE")


def market_timezone(market: str | None = "DSE") -> ZoneInfo:
    return _profile_for(market).tz


def market_open(market: str | None = "DSE") -> dt.time:
    return _profile_for(market).open_time


def market_close(market: str | None = "DSE") -> dt.time:
    return _profile_for(market).close_time


def to_market_tz(
    when: dt.datetime, tz: ZoneInfo | None = None, *, market: str | None = "DSE"
) -> dt.datetime:
    """Convert an aware datetime to the market timezone."""
    if when.tzinfo is None:
        raise ValueError("calendar requires timezone-aware datetimes")
    return when.astimezone(tz or market_timezone(market))


def is_trading_day(d: dt.date, *, market: str | None = "DSE") -> bool:
    """True on configured market weekdays that are not configured full-day holidays."""
    profile = _profile_for(market)
    return d.isoweekday() in profile.trading_isoweekdays and d not in profile.holidays


def add_trading_days(d: dt.date, n: int, *, market: str | None = "DSE") -> dt.date:
    """The date `n` trading days after `d`, skipping that market's weekends and holidays."""
    if n < 0:
        raise ValueError("n must be >= 0")
    out = d
    while n > 0:
        out += dt.timedelta(days=1)
        if is_trading_day(out, market=market):
            n -= 1
    return out


def is_trading_hours(
    when: dt.datetime, tz: ZoneInfo | None = None, *, market: str | None = "DSE"
) -> bool:
    """True if `when` falls inside the configured regular market session."""
    profile = _profile_for(market)
    local = to_market_tz(when, tz, market=market)
    return (
        is_trading_day(local.date(), market=profile.market)
        and profile.open_time <= local.time() <= profile.close_time
    )


def session_phase(
    when: dt.datetime, tz: ZoneInfo | None = None, *, market: str | None = "DSE"
) -> Session:
    """Which part of the market day `when` is in, in market time."""
    profile = _profile_for(market)
    local = to_market_tz(when, tz, market=market)
    if not is_trading_day(local.date(), market=profile.market):
        return Session.WEEKEND
    t = local.time()
    if t < profile.open_time:
        return Session.PRE_OPEN
    if t <= profile.close_time:
        return Session.OPEN
    return Session.POST_CLOSE
