"""Tests for the DSE trading calendar. Pure and deterministic.

Anchored to a known week:
  2026-06-21 Sun, 06-22 Mon, 06-25 Thu (trading) · 06-26 Fri, 06-27 Sat (closed).
Dhaka is UTC+6: 10:00 Dhaka == 04:00 UTC, 14:30 Dhaka == 08:30 UTC.
"""

from __future__ import annotations

import datetime as dt

import pytest

from bulls.market_data.calendar import (
    Session,
    add_trading_days,
    is_trading_day,
    is_trading_hours,
    session_phase,
    to_market_tz,
)


def _utc(y, m, d, hh, mm=0) -> dt.datetime:
    return dt.datetime(y, m, d, hh, mm, tzinfo=dt.UTC)


def test_is_trading_day():
    assert is_trading_day(dt.date(2026, 6, 21))  # Sunday
    assert is_trading_day(dt.date(2026, 6, 25))  # Thursday
    assert not is_trading_day(dt.date(2026, 6, 26))  # Friday
    assert not is_trading_day(dt.date(2026, 6, 27))  # Saturday
    assert not is_trading_day(dt.date(2026, 7, 1))  # public holiday (weekday, but market closed)


def test_is_trading_hours_boundaries():
    # Sunday session: 04:00-08:30 UTC (10:00-14:30 Dhaka)
    assert is_trading_hours(_utc(2026, 6, 21, 4, 0))  # open
    assert is_trading_hours(_utc(2026, 6, 21, 8, 30))  # close (inclusive)
    assert not is_trading_hours(_utc(2026, 6, 21, 3, 59))  # pre-open
    assert not is_trading_hours(_utc(2026, 6, 21, 8, 31))  # after close
    assert not is_trading_hours(_utc(2026, 6, 26, 5, 0))  # Friday - closed


def test_session_phase():
    assert session_phase(_utc(2026, 6, 21, 2, 0)) is Session.PRE_OPEN  # 08:00 Dhaka
    assert session_phase(_utc(2026, 6, 21, 5, 0)) is Session.OPEN  # 11:00 Dhaka
    assert session_phase(_utc(2026, 6, 21, 10, 0)) is Session.POST_CLOSE  # 16:00 Dhaka
    assert session_phase(_utc(2026, 6, 26, 5, 0)) is Session.WEEKEND  # Friday


def test_to_market_tz_requires_aware():
    with pytest.raises(ValueError, match="aware"):
        to_market_tz(dt.datetime(2026, 6, 21, 4, 0))  # naive
    # +6 offset applied (default Dhaka)
    assert to_market_tz(_utc(2026, 6, 21, 4, 0)).hour == 10


def test_add_trading_days_skips_weekend():
    # Sunday + 2 trading days = Tuesday (plain midweek case)
    assert add_trading_days(dt.date(2026, 6, 21), 2) == dt.date(2026, 6, 23)
    # Thursday + 2 trading days skips Fri/Sat: T+1 = Sun 06-28, T+2 = Mon 06-29
    assert add_trading_days(dt.date(2026, 6, 25), 2) == dt.date(2026, 6, 29)
    # Wednesday + 2: Thu, (Fri/Sat closed), Sun -> 06-24 + 2 = 06-28
    assert add_trading_days(dt.date(2026, 6, 24), 2) == dt.date(2026, 6, 28)


def test_add_trading_days_skips_holidays():
    # 2026-07-01 (Wed) is a public holiday: Mon 06-29 + 2 = Thu 07-02, not Wed 07-01
    assert add_trading_days(dt.date(2026, 6, 29), 2) == dt.date(2026, 7, 2)


def test_add_trading_days_zero_and_negative():
    assert add_trading_days(dt.date(2026, 6, 26), 0) == dt.date(2026, 6, 26)  # Friday unchanged
    with pytest.raises(ValueError):
        add_trading_days(dt.date(2026, 6, 21), -1)
