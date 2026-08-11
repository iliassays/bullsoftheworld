"""Tests for the promotion-blocking gates added by the phase-16 audit fixes.

These gates are the ones that decide whether a strategy can ever reach real capital, so a
silent regression in any of them is the most expensive kind of bug this repository can have —
it would not break a test, it would quietly let a dead strategy through. Each gate is
therefore exercised on both sides: the case that must fail, and the case that must pass.

Covers audit concerns #1 (30 bps kill rule, event-book market null), #2 (code constants inside
the frozen specification hash), #5 (cluster minimum), and #6 (explicit data-blocked refusal).
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.institutional_research.dse_squeeze_backtests import (
    _eligible_universe_equal_weight_null,
)
from api.institutional_research.institutional_backtests import (
    _CLUSTER_MINIMUM_INSIDERS,
    _EVENT_BOOK_POLICY_KWARGS,
    _unscreened_equal_weight_null,
    strategy_code_constants,
)
from api.institutional_research.investment import family_trial_count
from api.institutional_research.portfolio import data_blocked_refusal
from api.institutional_research.schemas import BacktestRequest
from api.institutional_research.workflow import (
    COST_SURVIVAL_FLOOR_BPS,
    _backtest_parameters,
    cost_survival_gate,
    event_market_null_gate,
)
from bulls.analytics.filing_book import CandidateEvent
from bulls.analytics.research_strategy import StrategyBar, StrategySecurity


@pytest.mark.asyncio
async def test_family_trial_count_is_scoped_to_the_research_organization() -> None:
    rows = [
        (
            {
                "request": {
                    "idempotency_key": key,
                    "strategy_key": "dse_reversal_v1",
                    "universe_limit": limit,
                }
            },
            f"legacy-{index}",
        )
        for index, (key, limit) in enumerate(
            (("retry-key-a", 25), ("retry-key-b", 25), ("new-test", 50))
        )
    ]
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: rows))
    )
    workspace = SimpleNamespace(
        organization_id="organization-a",
        tenant_id="bullsofdhaka",
        market="DSE",
    )

    assert await family_trial_count(
        session,
        workspace=workspace,
        strategy_key="dse_reversal_v1",
    ) == 2
    statement = session.execute.await_args.args[0]
    assert "research_strategy_trials.organization_id" in str(statement)


def test_backtest_frozen_parameters_exclude_transport_idempotency() -> None:
    first = BacktestRequest(
        idempotency_key="request-a",
        strategy_key="dse_reversal_v1",
        universe_limit=25,
    )
    retry = first.model_copy(update={"idempotency_key": "request-b"})

    assert _backtest_parameters(first) == _backtest_parameters(retry)
    assert "idempotency_key" not in _backtest_parameters(first)

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


# --- concern #1b: event books face a 1/N null, not only the placebo -------------------------


def _event(symbol: str, at: dt.datetime) -> CandidateEvent:
    return CandidateEvent(symbol=symbol, issuer_cik=1, kind="insider_cluster", signal_at=at)


def _sessions(count: int, start: dt.date = dt.date(2026, 1, 5)) -> list[dt.date]:
    return [start + dt.timedelta(days=index) for index in range(count)]


def test_null_equal_weights_every_event_and_sums_to_one() -> None:
    sessions = _sessions(10)
    at = dt.datetime.combine(sessions[1], dt.time.max, tzinfo=dt.UTC)
    schedule = _unscreened_equal_weight_null(
        candidates_by_session={at: [_event("AAA", at), _event("BBB", at)]},
        session_dates=sessions,
        time_stop_days=365,
    )
    assert schedule[sessions[1]] == {"AAA": 0.5, "BBB": 0.5}
    assert sum(schedule[sessions[1]].values()) == pytest.approx(1.0)


def test_null_never_holds_an_event_before_its_signal_session() -> None:
    """The null must not see an event earlier than the strategy did."""
    sessions = _sessions(10)
    at = dt.datetime.combine(sessions[4], dt.time.max, tzinfo=dt.UTC)
    schedule = _unscreened_equal_weight_null(
        candidates_by_session={at: [_event("AAA", at)]},
        session_dates=sessions,
        time_stop_days=365,
    )
    assert min(schedule) == sessions[4]
    assert all(as_of >= sessions[4] for as_of in schedule)


def test_null_ages_positions_out_on_the_books_time_stop() -> None:
    sessions = _sessions(12)
    at = dt.datetime.combine(sessions[0], dt.time.max, tzinfo=dt.UTC)
    schedule = _unscreened_equal_weight_null(
        candidates_by_session={at: [_event("AAA", at)]},
        session_dates=sessions,
        time_stop_days=5,
    )
    assert schedule[sessions[0]] == {"AAA": 1.0}
    # Entry at sessions[0] expires 5 days later, so sessions[5] holds nothing.
    assert schedule[sessions[5]] == {}


def test_null_emits_only_when_the_active_set_changes() -> None:
    """Mirrors the book's emit_unchanged=False; a rebalance every session is noise."""
    sessions = _sessions(8)
    at = dt.datetime.combine(sessions[2], dt.time.max, tzinfo=dt.UTC)
    schedule = _unscreened_equal_weight_null(
        candidates_by_session={at: [_event("AAA", at)]},
        session_dates=sessions,
        time_stop_days=365,
    )
    assert list(schedule) == [sessions[2]]


def test_null_is_unscreened_so_it_can_differ_from_the_book() -> None:
    """The whole point: the null holds names the book's screen would reject.

    A null built from the screened set would be a near-copy of the book and could never
    lose, which is the failure mode this construction exists to avoid.
    """
    sessions = _sessions(6)
    at = dt.datetime.combine(sessions[1], dt.time.max, tzinfo=dt.UTC)
    many = [_event(f"S{index}", at) for index in range(20)]
    schedule = _unscreened_equal_weight_null(
        candidates_by_session={at: many},
        session_dates=sessions,
        time_stop_days=365,
    )
    held = schedule[sessions[1]]
    # 20 names, while the book's policy caps concurrent positions at 20 and each at 5%.
    assert len(held) == 20
    assert _EVENT_BOOK_POLICY_KWARGS["max_position_pct"] == 0.05
    assert all(weight == pytest.approx(0.05) for weight in held.values())


def test_null_is_empty_without_sessions() -> None:
    assert (
        _unscreened_equal_weight_null(
            candidates_by_session={}, session_dates=[], time_stop_days=365
        )
        == {}
    )


# --- DSE symmetry: the DSE books get an equal-weight market null too ------------------------


def _dse_security(code: str, *, sessions: list[dt.date], value: float) -> StrategySecurity:
    """A security whose every session trades ``value`` in taka."""
    return StrategySecurity(
        code=code,
        sector="Unclassified",
        cap_tier="unclassified",
        bars=[
            StrategyBar(date=day, open=10.0, high=10.0, low=10.0, close=10.0, volume=value / 10.0)
            for day in sessions
        ],
    )


def test_dse_null_equal_weights_the_liquid_universe() -> None:
    sessions = _sessions(30)
    securities = [
        _dse_security("LIQA", sessions=sessions, value=10_000_000.0),
        _dse_security("LIQB", sessions=sessions, value=10_000_000.0),
    ]
    schedule = _eligible_universe_equal_weight_null(
        securities,
        rebalance_dates=[sessions[25]],
        minimum_average_daily_value_mn=2.0,
    )
    assert schedule[sessions[25]] == {"LIQA": 0.5, "LIQB": 0.5}


def test_dse_null_excludes_securities_below_the_liquidity_floor() -> None:
    """The null must be reachable — it cannot hold names the strategy could never trade."""
    sessions = _sessions(30)
    securities = [
        _dse_security("LIQ", sessions=sessions, value=10_000_000.0),
        _dse_security("THIN", sessions=sessions, value=100_000.0),
    ]
    schedule = _eligible_universe_equal_weight_null(
        securities,
        rebalance_dates=[sessions[25]],
        minimum_average_daily_value_mn=2.0,
    )
    assert schedule[sessions[25]] == {"LIQ": 1.0}


def test_dse_null_needs_a_full_trailing_window_before_admitting_a_name() -> None:
    """With fewer than 20 completed sessions the average is unknown, so the name abstains."""
    sessions = _sessions(30)
    securities = [_dse_security("LIQ", sessions=sessions, value=10_000_000.0)]
    early = _eligible_universe_equal_weight_null(
        securities,
        rebalance_dates=[sessions[5]],
        minimum_average_daily_value_mn=2.0,
    )
    assert early == {}


def test_dse_null_rebalances_on_every_strategy_decision_date() -> None:
    sessions = _sessions(30)
    securities = [_dse_security("LIQ", sessions=sessions, value=10_000_000.0)]
    schedule = _eligible_universe_equal_weight_null(
        securities,
        rebalance_dates=[sessions[22], sessions[25], sessions[28]],
        minimum_average_daily_value_mn=2.0,
    )
    assert list(schedule) == [sessions[22], sessions[25], sessions[28]]
    assert all(weights == {"LIQ": 1.0} for weights in schedule.values())


def test_dse_null_is_empty_without_rebalances() -> None:
    sessions = _sessions(30)
    securities = [_dse_security("LIQ", sessions=sessions, value=10_000_000.0)]
    assert (
        _eligible_universe_equal_weight_null(
            securities, rebalance_dates=[], minimum_average_daily_value_mn=2.0
        )
        == {}
    )


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
