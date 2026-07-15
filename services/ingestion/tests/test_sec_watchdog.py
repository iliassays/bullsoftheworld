from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from ingestion.sec_watchdog import _eod_cron_has_run, _eod_state_problems, _state_problems


def _state(
    source: str,
    now: dt.datetime,
    *,
    covered: int,
    details: dict | None = None,
    as_of_date: dt.date | None = None,
    records: int = 1,
):
    return SimpleNamespace(
        source=source,
        last_success_at=now,
        symbols_covered=covered,
        as_of_date=as_of_date,
        records=records,
        details=details or {},
    )


def test_regulatory_state_is_healthy_at_expected_depth_and_coverage() -> None:
    now = dt.datetime(2026, 7, 10, tzinfo=dt.UTC)
    states = {
        "sec_edgar": _state(
            "sec_edgar",
            now - dt.timedelta(hours=12),
            covered=60,
            details={"symbols_requested": 60, "symbols_failed": 0},
        ),
        "sec_13f": _state(
            "sec_13f",
            now - dt.timedelta(days=2),
            covered=58,
            details={"history_quarters_loaded": 8},
        ),
        "finra_short_volume": _state(
            "finra_short_volume",
            now - dt.timedelta(minutes=15),
            covered=55,
            as_of_date=dt.date(2026, 7, 9),
        ),
    }

    assert _state_problems(now, 60, states) == []  # type: ignore[arg-type]


def test_regulatory_state_reports_staleness_depth_coverage_and_failures() -> None:
    now = dt.datetime(2026, 7, 10, tzinfo=dt.UTC)
    states = {
        "sec_edgar": _state(
            "sec_edgar",
            now - dt.timedelta(hours=48),
            covered=50,
            details={"symbols_requested": 60, "symbols_failed": 10},
        ),
        "sec_13f": _state(
            "sec_13f",
            now - dt.timedelta(days=10),
            covered=40,
            details={"history_quarters_loaded": 4},
        ),
        "finra_short_volume": _state(
            "finra_short_volume",
            now - dt.timedelta(days=5),
            covered=0,
            as_of_date=dt.date(2026, 7, 8),
            records=0,
        ),
    }

    problems = _state_problems(now, 60, states)  # type: ignore[arg-type]

    assert len(problems) == 8
    assert any("48.0 hours old" in problem for problem in problems)
    assert any("4/8 quarters" in problem for problem in problems)


def test_eod_state_requires_due_session_coverage_and_analytics() -> None:
    due = dt.date(2026, 7, 10)
    next_day = dt.datetime(2026, 7, 11, 12, tzinfo=dt.UTC)  # well past the cron's own runtime
    assert _eod_state_problems(next_day, due, 60, due, 60, due, 0.9) == []

    problems = _eod_state_problems(
        next_day,
        due,
        60,
        dt.date(2026, 7, 9),
        50,
        dt.date(2026, 7, 9),
        0.9,
    )
    assert any("EOD bars latest 2026-07-09" in problem for problem in problems)
    assert any("analytics latest 2026-07-09" in problem for problem in problems)


def test_eod_state_enforces_configured_coverage_threshold() -> None:
    due = dt.date(2026, 7, 10)
    next_day = dt.datetime(2026, 7, 11, 12, tzinfo=dt.UTC)
    problems = _eod_state_problems(next_day, due, 60, due, 53, due, 0.9)
    assert problems == ["US EOD bars cover 53/60 symbols for 2026-07-10; required 54"]


def test_eod_cron_has_run_true_for_a_prior_day_regardless_of_clock() -> None:
    # A due_session from an earlier calendar day has had 22:45/23:30/01:30/13:30 UTC cycles
    # to fill in — never gated on the clock.
    assert _eod_cron_has_run(dt.datetime(2026, 7, 11, 0, 1, tzinfo=dt.UTC), dt.date(2026, 7, 10))


def test_eod_cron_has_not_run_yet_for_todays_due_session_before_2245_utc() -> None:
    # 2026-07-10 closes at 20:00 UTC (EDT); most_recent_due_session() already calls it "due" at
    # 21:30 UTC (close + 90min), a full hour before the 22:45 UTC cron has even attempted the
    # pull. This is exactly the 2026-07-15 false-positive: due-but-not-yet-attempted.
    due = dt.date(2026, 7, 10)
    assert not _eod_cron_has_run(dt.datetime(2026, 7, 10, 21, 30, tzinfo=dt.UTC), due)
    assert not _eod_cron_has_run(dt.datetime(2026, 7, 10, 22, 54, tzinfo=dt.UTC), due)


def test_eod_cron_has_run_for_todays_due_session_after_grace_window() -> None:
    due = dt.date(2026, 7, 10)
    assert _eod_cron_has_run(dt.datetime(2026, 7, 10, 22, 56, tzinfo=dt.UTC), due)


def test_eod_state_suppresses_coverage_alert_before_cron_has_attempted_the_pull() -> None:
    # The actual incident: due_session flips to today at 21:30 UTC, zero bars exist yet because
    # the 22:45 UTC cron hasn't run, and the old code alerted anyway.
    due = dt.date(2026, 7, 10)
    now = dt.datetime(2026, 7, 10, 21, 31, tzinfo=dt.UTC)
    assert _eod_state_problems(now, due, 60, dt.date(2026, 7, 9), 0, dt.date(2026, 7, 9), 0.9) == []
