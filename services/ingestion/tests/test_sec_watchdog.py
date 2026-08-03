from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

import pytest

from ingestion.sec_watchdog import (
    _eod_cron_has_run,
    _eod_recovery_action,
    _eod_state_problems,
    _send_alert,
    _state_problems,
    _status_event,
)


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


def test_sec_coverage_uses_the_sec_target_scope_not_all_ready_instruments() -> None:
    now = dt.datetime(2026, 7, 28, tzinfo=dt.UTC)
    states = {
        "sec_edgar": _state(
            "sec_edgar",
            now,
            covered=60,
            details={"symbols_requested": 60, "symbols_failed": 0},
        ),
        "sec_13f": _state(
            "sec_13f",
            now,
            covered=100,
            details={"history_quarters_loaded": 8},
        ),
        "finra_short_volume": _state(
            "finra_short_volume",
            now,
            covered=100,
            as_of_date=dt.date(2026, 7, 27),
        ),
    }

    assert (
        _state_problems(  # type: ignore[arg-type]
            now,
            100,
            states,
            sec_target_symbols=60,
        )
        == []
    )


def test_sec_coverage_failure_names_the_targetable_denominator() -> None:
    now = dt.datetime(2026, 7, 28, tzinfo=dt.UTC)
    states = {
        "sec_edgar": _state("sec_edgar", now, covered=50),
        "sec_13f": _state(
            "sec_13f",
            now,
            covered=100,
            details={"history_quarters_loaded": 8},
        ),
        "finra_short_volume": _state(
            "finra_short_volume",
            now,
            covered=100,
            as_of_date=dt.date(2026, 7, 27),
        ),
    }

    problems = _state_problems(  # type: ignore[arg-type]
        now,
        100,
        states,
        sec_target_symbols=60,
    )

    assert problems == ["SEC EDGAR covers 50/60 SEC-targetable symbols"]


def test_status_event_fingerprint_changes_only_when_health_state_changes() -> None:
    now = dt.datetime(2026, 7, 28, 10, 5, tzinfo=dt.UTC)
    first_fingerprint, payload = _status_event(
        now,
        ["SEC EDGAR covers 50/60 SEC-targetable symbols"],
        [],
        email_scheduled=True,
    )
    repeat_fingerprint, _ = _status_event(
        now + dt.timedelta(minutes=30),
        ["SEC EDGAR covers 50/60 SEC-targetable symbols"],
        [],
        email_scheduled=False,
    )
    healthy_fingerprint, healthy_payload = _status_event(
        now + dt.timedelta(hours=1),
        [],
        [],
        email_scheduled=False,
    )

    assert first_fingerprint == repeat_fingerprint
    assert healthy_fingerprint != first_fingerprint
    assert '"email_scheduled": true' in payload
    assert '"status": "healthy"' in healthy_payload


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


def test_finra_state_reports_symbol_mapping_coverage_regression() -> None:
    now = dt.datetime(2026, 7, 10, tzinfo=dt.UTC)
    states = {
        "sec_edgar": _state("sec_edgar", now, covered=60),
        "sec_13f": _state(
            "sec_13f",
            now,
            covered=60,
            details={"history_quarters_loaded": 8},
        ),
        "finra_short_volume": _state(
            "finra_short_volume",
            now,
            covered=700,
            as_of_date=dt.date(2026, 7, 9),
            details={"latest_source_rows": 1_000, "latest_stored_rows": 700},
        ),
    }

    problems = _state_problems(now, 60, states)  # type: ignore[arg-type]

    assert problems == ["FINRA short-volume symbol match coverage fell to 700/1000 (70.0%)"]


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


def test_eod_recovery_is_active_while_a_fresh_attempt_is_running() -> None:
    due = dt.date(2026, 7, 31)
    now = dt.datetime(2026, 8, 1, 0, 0, tzinfo=dt.UTC)
    state = {
        "session_date": due.isoformat(),
        "status": "running",
        "stage": "pulling_missing_bars",
        "attempt": 2,
        "updated_at": (now - dt.timedelta(minutes=30)).isoformat(),
    }

    assert _eod_recovery_action(json.dumps(state), now, due) == (
        "US EOD recovery attempt 2 is running (pulling_missing_bars)"
    )


def test_eod_recovery_stops_suppressing_alerts_after_bounded_retries() -> None:
    due = dt.date(2026, 7, 31)
    now = dt.datetime(2026, 8, 1, 2, 0, tzinfo=dt.UTC)
    state = {
        "session_date": due.isoformat(),
        "status": "retry_pending",
        "stage": "coverage_gate",
        "attempt": 4,
        "updated_at": (now - dt.timedelta(minutes=20)).isoformat(),
    }

    assert _eod_recovery_action(json.dumps(state), now, due) is None


@pytest.mark.asyncio
async def test_empty_health_alert_is_suppressed_before_email_configuration() -> None:
    await _send_alert([], [])
