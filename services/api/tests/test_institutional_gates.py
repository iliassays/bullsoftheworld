"""Tests for the promotion-blocking gates added by the phase-16 audit fixes.

These gates are the ones that decide whether a strategy can ever reach real capital, so a
silent regression in any of them is the most expensive kind of bug this repository can have —
it would not break a test, it would quietly let a dead strategy through. Each gate is
therefore exercised on both sides: the case that must fail, and the case that must pass.

Covers audit concerns #1 (30 bps kill rule, event-book market null), #2 (code constants inside
the frozen specification hash), #5 (cluster minimum), and #6 (explicit data-blocked refusal).
"""

from __future__ import annotations

import pytest

from api.institutional_research.institutional_backtests import (
    _CLUSTER_MINIMUM_INSIDERS,
    _EVENT_BOOK_POLICY_KWARGS,
    strategy_code_constants,
)
from api.institutional_research.portfolio import data_blocked_refusal
from api.institutional_research.workflow import (
    COST_SURVIVAL_FLOOR_BPS,
    cost_survival_gate,
    event_market_null_gate,
)

# --- concern #1a: the 30 bps kill rule is a gate, not a metric ------------------------------


def test_edge_dying_at_or_below_the_cost_floor_fails_the_run() -> None:
    for dies_at in (10.0, 30.0):
        reason = cost_survival_gate(dies_at)
        assert reason is not None, f"edge dying at {dies_at} bps must fail the gate"
        assert "phase 13" in reason


def test_edge_surviving_past_the_cost_floor_passes() -> None:
    assert cost_survival_gate(50.0) is None


def test_edge_that_never_dies_passes() -> None:
    """``None`` means no stress tier killed the edge — the only genuinely passing case."""
    assert cost_survival_gate(None) is None


def test_cost_floor_is_the_documented_thirty_bps() -> None:
    assert COST_SURVIVAL_FLOOR_BPS == 30.0


# --- concern #1b: event books face a market null, not only the placebo ----------------------


def _null_gate(*, final_nav: float, benchmark_final: float, stress_30: float | None):
    return event_market_null_gate(
        strategy_key="us_activist_13d_v1",
        benchmark_valid=True,
        initial_capital=1_000_000.0,
        benchmark_final=benchmark_final,
        final_nav=final_nav,
        stress_30_net_return_pct=stress_30,
    )


def test_event_book_beating_the_market_at_both_cost_bases_passes() -> None:
    summary, failure = _null_gate(
        final_nav=1_200_000.0, benchmark_final=1_100_000.0, stress_30=15.0
    )
    assert failure is None
    assert summary == {
        "benchmark_return_pct": 10.0,
        "strategy_beats_realistic": True,
        "strategy_beats_stress_30bps": True,
    }


def test_event_book_trailing_the_market_fails() -> None:
    summary, failure = _null_gate(final_nav=1_050_000.0, benchmark_final=1_100_000.0, stress_30=4.0)
    assert failure is not None
    assert "phase 12 market null" in failure
    assert summary["strategy_beats_realistic"] is False


def test_event_book_that_only_wins_before_cost_stress_fails() -> None:
    """Beating the market at realistic cost but not at 30 bps is not a pass."""
    summary, failure = _null_gate(final_nav=1_150_000.0, benchmark_final=1_100_000.0, stress_30=8.0)
    assert failure is not None
    assert summary["strategy_beats_realistic"] is True
    assert summary["strategy_beats_stress_30bps"] is False


def test_missing_stress_figure_fails_closed() -> None:
    """An unmeasurable comparison must never count as a passed comparison."""
    _summary, failure = _null_gate(
        final_nav=1_500_000.0, benchmark_final=1_100_000.0, stress_30=None
    )
    assert failure is not None


def test_non_event_books_are_not_subject_to_this_gate() -> None:
    summary, failure = event_market_null_gate(
        strategy_key="us_factor_sleeve_v1",
        benchmark_valid=True,
        initial_capital=1_000_000.0,
        benchmark_final=1_100_000.0,
        final_nav=1_000_000.0,
        stress_30_net_return_pct=0.0,
    )
    assert (summary, failure) == (None, None)


def test_gate_abstains_when_the_benchmark_is_invalid() -> None:
    """Without a valid benchmark there is nothing to compare against; do not invent a verdict."""
    summary, failure = event_market_null_gate(
        strategy_key="us_activist_13d_v1",
        benchmark_valid=False,
        initial_capital=1_000_000.0,
        benchmark_final=0.0,
        final_nav=1_200_000.0,
        stress_30_net_return_pct=15.0,
    )
    assert (summary, failure) == (None, None)


# --- concern #2: code-resident constants live inside the frozen specification ---------------


@pytest.mark.parametrize("strategy_key", ["us_activist_13d_v1", "us_insider_cluster_v1"])
def test_event_strategies_publish_their_code_constants(strategy_key: str) -> None:
    constants = strategy_code_constants(strategy_key)
    assert constants is not None
    assert constants["book_policy"] == _EVENT_BOOK_POLICY_KWARGS
    assert constants["placebo_delay_sessions"] == 21


def test_activist_roster_is_part_of_the_specification() -> None:
    constants = strategy_code_constants("us_activist_13d_v1")
    assert constants is not None
    roster = constants["activist_roster_fragments"]
    assert roster == sorted(roster), "roster must be order-stable or the hash is not reproducible"
    assert len(roster) > 0


def test_editing_a_constant_changes_the_specification_hash() -> None:
    """The point of concern #2: a changed roster must not reuse a frozen trial's hash."""
    from api.institutional_research.workflow import _stable_hash

    baseline = strategy_code_constants("us_activist_13d_v1")
    assert baseline is not None
    edited = dict(baseline)
    edited["activist_roster_fragments"] = [*baseline["activist_roster_fragments"], "new fund lp"]

    assert _stable_hash({"code_constants": baseline}) != _stable_hash({"code_constants": edited})


def test_non_event_strategies_have_no_code_constants() -> None:
    assert strategy_code_constants("us_factor_sleeve_v1") is None


# --- concern #5: the insider sleeve requires a real cluster ---------------------------------


def test_insider_cluster_requires_at_least_two_insiders() -> None:
    """Phase 12's evidence is about multiple insiders; singletons are not a cluster."""
    assert _CLUSTER_MINIMUM_INSIDERS == 2
    constants = strategy_code_constants("us_insider_cluster_v1")
    assert constants is not None
    assert constants["cluster_minimum_insiders"] == 2


# --- concern #6: the data-blocked refusal is explicit ---------------------------------------


def test_run_with_no_simulated_sessions_is_refused() -> None:
    reason = data_blocked_refusal({"equity_curve": [], "trades": []})
    assert reason is not None
    assert "data-blocked" in reason


def test_run_with_a_simulated_equity_curve_is_allowed() -> None:
    assert data_blocked_refusal({"equity_curve": [{"date": "2026-01-02"}], "trades": []}) is None


def test_run_with_trades_but_no_curve_is_allowed() -> None:
    """A book can trade without a persisted curve; only a wholly empty result is a refusal."""
    assert data_blocked_refusal({"equity_curve": [], "trades": [{"code": "AAPL"}]}) is None
