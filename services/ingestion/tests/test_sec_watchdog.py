from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from ingestion.sec_watchdog import _eod_state_problems, _state_problems


def _state(source: str, now: dt.datetime, *, covered: int, details: dict | None = None):
    return SimpleNamespace(
        source=source,
        last_success_at=now,
        symbols_covered=covered,
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
    }

    problems = _state_problems(now, 60, states)  # type: ignore[arg-type]

    assert len(problems) == 6
    assert any("48.0 hours old" in problem for problem in problems)
    assert any("4/8 quarters" in problem for problem in problems)


def test_eod_state_requires_due_session_coverage_and_analytics() -> None:
    due = dt.date(2026, 7, 10)
    assert _eod_state_problems(due, 60, due, 60, due, 0.9) == []

    problems = _eod_state_problems(
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
    problems = _eod_state_problems(due, 60, due, 53, due, 0.9)
    assert problems == ["US EOD bars cover 53/60 symbols for 2026-07-10; required 54"]
