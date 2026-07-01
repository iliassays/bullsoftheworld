"""Market trading calendar - pure, timezone-correct helpers.

A market's trading hours and timezone are configuration, not hardcoded: every function takes an
explicit `tz` (surfaced through tenant config), so the same logic serves any exchange. DSE's
Asia/Dhaka is the default. DSE trades Sunday to Thursday, 10:00-14:30, closed Friday/Saturday and
on public holidays (see MARKET_HOLIDAYS).

Inputs must be timezone-AWARE datetimes (e.g. datetime.now(dt.UTC)); they're converted to `tz`.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from zoneinfo import ZoneInfo

DHAKA = ZoneInfo("Asia/Dhaka")
MARKET_OPEN = dt.time(10, 0)
MARKET_CLOSE = dt.time(14, 30)

# isoweekday(): Mon=1 .. Sun=7. DSE trades Sun, Mon, Tue, Wed, Thu.
_TRADING_ISOWEEKDAYS = frozenset({7, 1, 2, 3, 4})

# DSE public holidays — the market is closed even though it's a weekday. Maintain from DSE's
# official annual holiday calendar (dates are Dhaka-local). Under-listing only costs a benign
# watchdog false-alarm that day; over-listing would make the worker skip a REAL trading day, so
# add only confirmed dates.
MARKET_HOLIDAYS: frozenset[dt.date] = frozenset(
    {
        dt.date(2026, 7, 1),  # confirmed closed — extend with the official DSE 2026 calendar
    }
)


class Session(StrEnum):
    PRE_OPEN = "pre_open"  # trading day, before open
    OPEN = "open"  # within market hours
    POST_CLOSE = "post_close"  # trading day, after close
    WEEKEND = "weekend"  # non-trading day


def to_market_tz(when: dt.datetime, tz: ZoneInfo = DHAKA) -> dt.datetime:
    """Convert an aware datetime to the market timezone."""
    if when.tzinfo is None:
        raise ValueError("calendar requires timezone-aware datetimes")
    return when.astimezone(tz)


def is_trading_day(d: dt.date) -> bool:
    """True on Sun-Thu that aren't public holidays."""
    return d.isoweekday() in _TRADING_ISOWEEKDAYS and d not in MARKET_HOLIDAYS


def is_trading_hours(when: dt.datetime, tz: ZoneInfo = DHAKA) -> bool:
    """True if `when` falls inside a session (trading day, 10:00-14:30 market time)."""
    local = to_market_tz(when, tz)
    return is_trading_day(local.date()) and MARKET_OPEN <= local.time() <= MARKET_CLOSE


def session_phase(when: dt.datetime, tz: ZoneInfo = DHAKA) -> Session:
    """Which part of the market day `when` is in, in market time."""
    local = to_market_tz(when, tz)
    if not is_trading_day(local.date()):
        return Session.WEEKEND
    t = local.time()
    if t < MARKET_OPEN:
        return Session.PRE_OPEN
    if t <= MARKET_CLOSE:
        return Session.OPEN
    return Session.POST_CLOSE
