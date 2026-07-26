from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from api.institutional_research.portfolio import (
    promotion_evidence_window,
    shadow_creation_admission_error,
)


def snapshot(day: int, nav: float, trades: int = 0):
    return SimpleNamespace(
        as_of_date=dt.date(2026, 7, day),
        nav=nav,
        trades=[{}] * trades,
    )


def test_retroactive_replay_is_excluded_from_forward_evidence() -> None:
    rows = [
        snapshot(1, 100),
        snapshot(2, 104, 1),
        snapshot(3, 98, 1),
        snapshot(6, 102),
        snapshot(7, 99, 1),
    ]

    baseline, latest, observations, drawdown = promotion_evidence_window(
        rows,
        forward_started_on=dt.date(2026, 7, 6),
    )

    assert baseline.as_of_date == dt.date(2026, 7, 3)
    assert latest.as_of_date == dt.date(2026, 7, 7)
    assert [item.as_of_date.day for item in observations] == [6, 7]
    assert drawdown == pytest.approx((1 - 99 / 102) * 100)


def test_ordinary_forward_book_uses_inception_as_baseline() -> None:
    rows = [snapshot(1, 100), snapshot(2, 101), snapshot(3, 99)]

    baseline, latest, observations, drawdown = promotion_evidence_window(
        rows,
        forward_started_on=dt.date(2026, 7, 1),
    )

    assert baseline is rows[0]
    assert latest is rows[-1]
    assert observations == rows[1:]
    assert drawdown == pytest.approx((1 - 99 / 101) * 100)


def test_future_forward_boundary_has_zero_forward_observations() -> None:
    rows = [snapshot(1, 100), snapshot(2, 103)]

    baseline, latest, observations, drawdown = promotion_evidence_window(
        rows,
        forward_started_on=dt.date(2026, 7, 3),
    )

    assert baseline is rows[-1]
    assert latest is rows[-1]
    assert observations == []
    assert drawdown == 0


def test_selective_shadow_creation_fails_closed_without_admission() -> None:
    missing = shadow_creation_admission_error("dse_selective_compression_v1", {})
    failed = shadow_creation_admission_error(
        "dse_selective_compression_v1",
        {
            "result_summary": {
                "forward_observation_admission": {
                    "passed": False,
                    "failed_checks": ["positive_test_excess_return"],
                }
            }
        },
    )
    passed = shadow_creation_admission_error(
        "dse_selective_compression_v1",
        {"result_summary": {"forward_observation_admission": {"passed": True}}},
    )

    assert "evidence is missing" in (missing or "")
    assert "positive_test_excess_return" in (failed or "")
    assert passed is None


def test_broad_compression_shadow_creation_remains_paused() -> None:
    reason = shadow_creation_admission_error("dse_compression_breakout_20d_v1", {})

    assert reason is not None
    assert "failed its historical diagnostic" in reason


def test_benchmark_independence_requires_explicit_series_for_the_whole_window() -> None:
    from api.institutional_research.portfolio import (
        benchmark_independent_for_window,
        explicit_benchmark_since,
    )

    observations = [snapshot(6, 102), snapshot(7, 99)]

    # No explicit series ever wired: diagnostic.
    assert not benchmark_independent_for_window({}, observations)
    # Switched mid-window (after the first observation): still diagnostic — a mixed ratio
    # is meaningless.
    assert not benchmark_independent_for_window(
        {"benchmark_explicit_since": "2026-07-07"}, observations
    )
    # Explicit from the first observation onward: independent.
    assert benchmark_independent_for_window(
        {"benchmark_explicit_since": "2026-07-06"}, observations
    )
    # Empty windows can never claim independence.
    assert not benchmark_independent_for_window({"benchmark_explicit_since": "2026-07-01"}, [])
    # Corrupt values parse to None instead of raising during a refresh.
    assert explicit_benchmark_since({"benchmark_explicit_since": "not-a-date"}) is None
