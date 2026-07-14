from __future__ import annotations

import datetime as dt

from ingestion.history import _is_ready
from ingestion.us_worker import _completion_key, most_recent_due_session


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(year, month, day, hour, minute, tzinfo=dt.UTC)


def test_due_session_waits_for_eod_publication_window() -> None:
    # 2026-07-09 closes at 20:00 UTC; before 21:30, the prior session is still the due one.
    assert most_recent_due_session(_utc(2026, 7, 9, 21, 29)) == dt.date(2026, 7, 8)
    assert most_recent_due_session(_utc(2026, 7, 9, 21, 30)) == dt.date(2026, 7, 9)


def test_due_session_handles_weekends_and_early_closes() -> None:
    assert most_recent_due_session(_utc(2026, 7, 12, 12)) == dt.date(2026, 7, 10)
    # 2026-11-27 closes at 18:00 UTC, so its EOD window opens at 19:30 UTC.
    assert most_recent_due_session(_utc(2026, 11, 27, 19, 30)) == dt.date(2026, 11, 27)


def test_us_publication_readiness_requires_depth_and_freshness() -> None:
    end = dt.date(2026, 7, 9)
    assert _is_ready(252, end, end)
    assert not _is_ready(251, end, end)
    assert not _is_ready(252, dt.date(2026, 6, 28), end)


def test_eod_completion_marker_is_tenant_and_session_specific() -> None:
    assert _completion_key(dt.date(2026, 7, 9)) == (
        "ingestion:bullsofwallst:eod-complete:v2:2026-07-09"
    )
