"""Every cron entry must be schedulable — a bad weekday/hour spec crash-loops the WHOLE worker.

This exact failure happened on 2026-07-03: weekday="sun,mon,tues,wed,thurs" (a comma-joined
string, which arq does not accept) took down every scheduled job until the next deploy.
"""

from __future__ import annotations

import datetime as dt

from ingestion.research_worker import WorkerSettings as ResearchWorkerSettings
from ingestion.sec_worker import WorkerSettings as SecWorkerSettings
from ingestion.us_worker import WorkerSettings as UsWorkerSettings
from ingestion.worker import (
    COMPANY_REFRESH_TIMEOUT_SECONDS,
    FINAL_QUOTE_UTC_HOUR,
    FINAL_QUOTE_UTC_MINUTE,
    WorkerSettings,
    _after_eod_window,
    _after_market_date_utc_time,
    _eod_completion_key,
)


def test_every_cron_job_can_calculate_its_next_run() -> None:
    now = dt.datetime(2026, 7, 1, 0, 0, tzinfo=dt.UTC)
    worker_settings = (
        WorkerSettings,
        ResearchWorkerSettings,
        UsWorkerSettings,
        SecWorkerSettings,
    )
    for settings in worker_settings:
        for job in settings.cron_jobs:
            job.calculate_next(now)  # raises on any invalid spec (e.g. bad weekday string)
            assert job.next_run is not None, job.name


def test_sec_archive_downloads_never_run_at_worker_startup() -> None:
    jobs = {job.name: job for job in SecWorkerSettings.cron_jobs}

    assert not jobs["cron:refresh_sec_company_data"].run_at_startup
    assert not jobs["cron:refresh_sec_institutional_data"].run_at_startup
    assert jobs["cron:evaluate_stored_regulatory_agents"].run_at_startup
    assert SecWorkerSettings.retry_jobs is False


def test_eod_startup_recovery_is_time_guarded() -> None:
    assert not _after_eod_window(dt.datetime(2026, 7, 8, 8, 30, tzinfo=dt.UTC))
    assert _after_eod_window(dt.datetime(2026, 7, 8, 11, 0, tzinfo=dt.UTC))
    # 22:00 UTC is already the next Dhaka date, but that market date's EOD is still in the future.
    assert not _after_eod_window(dt.datetime(2026, 7, 8, 22, 0, tzinfo=dt.UTC))


def test_final_delayed_quote_poll_recovers_on_startup() -> None:
    jobs = {job.name: job for job in WorkerSettings.cron_jobs}
    final_poll = jobs["cron:finalize_quotes"]

    assert final_poll.run_at_startup
    assert final_poll.hour == FINAL_QUOTE_UTC_HOUR
    assert final_poll.minute == FINAL_QUOTE_UTC_MINUTE


def test_weekly_company_refresh_has_a_realistic_bounded_timeout() -> None:
    jobs = {job.name: job for job in WorkerSettings.cron_jobs}

    assert jobs["cron:refresh_company"].timeout_s == COMPANY_REFRESH_TIMEOUT_SECONDS
    assert COMPANY_REFRESH_TIMEOUT_SECONDS == 30 * 60


def test_market_date_utc_guard_handles_dhaka_rollover() -> None:
    market_date = dt.date(2026, 7, 9)

    assert not _after_market_date_utc_time(
        dt.datetime(2026, 7, 8, 22, 0, tzinfo=dt.UTC), market_date, 3, 30
    )
    assert _after_market_date_utc_time(
        dt.datetime(2026, 7, 9, 3, 30, tzinfo=dt.UTC), market_date, 3, 30
    )


def test_dse_eod_completion_marker_is_tenant_session_and_version_specific() -> None:
    assert _eod_completion_key(dt.date(2026, 7, 9)) == (
        "ingestion:bullsofdhaka:eod-complete:v2:2026-07-09"
    )
