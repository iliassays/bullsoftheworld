"""Pure watchdog time-window tests.

These protect the Dhaka-date/UTC-date boundary. At 22:00 UTC the Dhaka calendar has already rolled
to tomorrow, but tomorrow's UTC-scheduled jobs are still hours in the future.
"""

from __future__ import annotations

import datetime as dt

from ingestion.watchdog import MORNING_WATCH_CHECK_FROM_UTC_HOUR, _utc_check_start


def test_morning_watch_check_waits_for_the_market_dates_utc_window() -> None:
    market_date = dt.date(2026, 7, 9)

    assert dt.datetime(2026, 7, 8, 22, 4, tzinfo=dt.UTC) < _utc_check_start(
        market_date, MORNING_WATCH_CHECK_FROM_UTC_HOUR
    )
    assert dt.datetime(2026, 7, 9, 5, 0, tzinfo=dt.UTC) >= _utc_check_start(
        market_date, MORNING_WATCH_CHECK_FROM_UTC_HOUR
    )
