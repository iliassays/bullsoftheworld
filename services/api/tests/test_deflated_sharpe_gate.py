"""Unit tests for the deflated-Sharpe promotion gate glue in the backtest workflow.

The DSR math itself is covered in packages/analytics; these tests cover the workflow-layer
glue: turning a backtest equity curve + trial count into a promotion gate decision.
"""

from __future__ import annotations

import random

from api.institutional_research.workflow import _deflated_sharpe_gate
from bulls.analytics.research_strategy import EquityPoint


def _curve(*, drift: float, vol: float, n: int, seed: int) -> list[EquityPoint]:
    rng = random.Random(seed)
    nav = 100_000.0
    points: list[EquityPoint] = []
    for _ in range(n):
        nav *= 1.0 + rng.gauss(drift, vol)
        points.append(
            EquityPoint(
                date=__import__("datetime").date(2024, 1, 1),
                nav=round(nav, 2),
                benchmark=100_000.0,
                cash=0.0,
                gross_exposure_pct=90.0,
                drawdown_pct=0.0,
            )
        )
    return points


def test_gate_reports_none_and_blocks_when_history_too_thin() -> None:
    summary, failed = _deflated_sharpe_gate(_curve(drift=0.001, vol=0.01, n=5, seed=1), num_trials=1)
    assert summary is None
    assert failed is not None
    assert "could not be computed" in failed


def test_strong_single_trial_curve_clears_the_gate() -> None:
    summary, failed = _deflated_sharpe_gate(
        _curve(drift=0.0012, vol=0.008, n=800, seed=3), num_trials=1
    )
    assert failed is None
    assert summary is not None
    assert summary["passes"] is True
    assert summary["num_trials"] == 1


def test_same_curve_fails_the_gate_under_heavy_multiple_testing() -> None:
    curve = _curve(drift=0.0012, vol=0.008, n=800, seed=3)
    _, single_trial = _deflated_sharpe_gate(curve, num_trials=1)
    summary, many_trials = _deflated_sharpe_gate(curve, num_trials=5000)
    assert single_trial is None  # convincing on its own
    assert many_trials is not None  # not convincing once you tried 5000 specs to find it
    assert summary is not None and summary["passes"] is False
    assert "5000 trial" in many_trials


def test_gate_summary_carries_the_diagnostic_numbers() -> None:
    summary, _ = _deflated_sharpe_gate(_curve(drift=0.001, vol=0.01, n=400, seed=9), num_trials=10)
    assert summary is not None
    for key in ("probabilistic_sharpe", "deflated_sharpe", "benchmark_sharpe", "moments"):
        assert key in summary
