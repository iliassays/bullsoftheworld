"""Every cron entry must be schedulable — a bad weekday/hour spec crash-loops the WHOLE worker.

This exact failure happened on 2026-07-03: weekday="sun,mon,tues,wed,thurs" (a comma-joined
string, which arq does not accept) took down every scheduled job until the next deploy.
"""

from __future__ import annotations

import datetime as dt

from ingestion.worker import WorkerSettings, _after_eod_window, _after_market_date_utc_time


def test_every_cron_job_can_calculate_its_next_run() -> None:
    now = dt.datetime(2026, 7, 1, 0, 0, tzinfo=dt.UTC)
    for job in WorkerSettings.cron_jobs:
        job.calculate_next(now)  # raises on any invalid spec (e.g. bad weekday string)
        assert job.next_run is not None, job.name


def test_eod_startup_recovery_is_time_guarded() -> None:
    assert not _after_eod_window(dt.datetime(2026, 7, 8, 8, 30, tzinfo=dt.UTC))
    assert _after_eod_window(dt.datetime(2026, 7, 8, 13, 0, tzinfo=dt.UTC))
    # 22:00 UTC is already the next Dhaka date, but that market date's EOD is still in the future.
    assert not _after_eod_window(dt.datetime(2026, 7, 8, 22, 0, tzinfo=dt.UTC))


def test_market_date_utc_guard_handles_dhaka_rollover() -> None:
    market_date = dt.date(2026, 7, 9)

    assert not _after_market_date_utc_time(
        dt.datetime(2026, 7, 8, 22, 0, tzinfo=dt.UTC), market_date, 3, 30
    )
    assert _after_market_date_utc_time(
        dt.datetime(2026, 7, 9, 3, 30, tzinfo=dt.UTC), market_date, 3, 30
    )
