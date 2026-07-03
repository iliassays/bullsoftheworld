"""Every cron entry must be schedulable — a bad weekday/hour spec crash-loops the WHOLE worker.

This exact failure happened on 2026-07-03: weekday="sun,mon,tues,wed,thurs" (a comma-joined
string, which arq does not accept) took down every scheduled job until the next deploy.
"""

from __future__ import annotations

import datetime as dt

from ingestion.worker import WorkerSettings


def test_every_cron_job_can_calculate_its_next_run() -> None:
    now = dt.datetime(2026, 7, 1, 0, 0, tzinfo=dt.UTC)
    for job in WorkerSettings.cron_jobs:
        job.calculate_next(now)  # raises on any invalid spec (e.g. bad weekday string)
        assert job.next_run is not None, job.name
