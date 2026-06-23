"""DSE trading calendar - pure, timezone-correct helpers.

All scheduling correctness lives here (not in arq's clock), so it's unit-testable and independent
of where the worker runs. DSE trades Sunday to Thursday, 10:00-14:30 Asia/Dhaka (UTC+6, no DST),
and is closed Friday/Saturday. Public holidays are not yet modeled (a future calendar feed) - on a
holiday the scraper simply returns the previous session's data, and the upsert is idempotent.

Inputs must be timezone-AWARE datetimes (e.g. datetime.now(dt.UTC)); they're converted to Dhaka.
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


class Session(StrEnum):
    PRE_OPEN = "pre_open"  # trading day, before open
    OPEN = "open"  # within 10:00-14:30
    POST_CLOSE = "post_close"  # trading day, after close
    WEEKEND = "weekend"  # Fri/Sat


def to_dhaka(when: dt.datetime) -> dt.datetime:
    """Convert an aware datetime to Asia/Dhaka."""
    if when.tzinfo is None:
        raise ValueError("market_calendar requires timezone-aware datetimes")
    return when.astimezone(DHAKA)


def is_trading_day(d: dt.date) -> bool:
    """True for Sun-Thu (holidays not yet modeled)."""
    return d.isoweekday() in _TRADING_ISOWEEKDAYS


def is_trading_hours(when: dt.datetime) -> bool:
    """True if `when` falls inside a DSE session (trading day, 10:00-14:30 Dhaka)."""
    local = to_dhaka(when)
    return is_trading_day(local.date()) and MARKET_OPEN <= local.time() <= MARKET_CLOSE


def session_phase(when: dt.datetime) -> Session:
    """Which part of the market day `when` is in, in Dhaka time."""
    local = to_dhaka(when)
    if not is_trading_day(local.date()):
        return Session.WEEKEND
    t = local.time()
    if t < MARKET_OPEN:
        return Session.PRE_OPEN
    if t <= MARKET_CLOSE:
        return Session.OPEN
    return Session.POST_CLOSE
