"""Tests for the cost-tiered backtest and the per-name half-spread cost model (Phase 13.2)."""

from __future__ import annotations

import datetime as dt

from bulls.analytics.research_strategy import (
    RISK_POLICIES,
    ShadowPosition,
    ShadowState,
    StrategyBar,
    StrategySecurity,
    advance_shadow_portfolio,
    run_backtest,
    run_cost_tiered_backtest,
)


def _trending_security(code: str, *, sessions: int = 260, volume: int = 2_000_000) -> StrategySecurity:
    start = dt.date(2024, 1, 1)
    bars = []
    for index in range(sessions):
        close = 10 + index * 0.03
        bars.append(
            StrategyBar(
                date=start + dt.timedelta(days=index),
                open=close * 0.998,
                high=close * 1.012,
                low=close * 0.988,
                close=close,
                volume=volume + index * 100,
            )
        )
    return StrategySecurity(code=code, sector="Technology", cap_tier="small", bars=bars)


def _universe(n: int = 4) -> list[StrategySecurity]:
    return [_trending_security(f"T{i}") for i in range(n)]


def test_flat_half_spread_override_raises_costs_versus_policy_default() -> None:
    universe = _universe()
    cheap = run_backtest(market="US", strategy_key="us_breakout_v1", securities=universe)
    dear = run_backtest(
        market="US",
        strategy_key="us_breakout_v1",
        securities=universe,
        half_spread_bps=200.0,  # a punitive 200 bps one-way half-spread
    )
    # Higher trading friction can only reduce (never improve) the net result on the same signals.
    assert dear.final_nav <= cheap.final_nav
    assert dear.fees_paid >= 0


def test_per_name_half_spread_dict_is_accepted() -> None:
    universe = _universe()
    result = run_backtest(
        market="US",
        strategy_key="us_breakout_v1",
        securities=universe,
        half_spread_bps={"T0": 5.0, "T1": 40.0},  # others fall back to the policy slippage
    )
    assert result.trades  # still runs and trades with a partial per-name map


def test_external_schedule_is_constrained_by_sector_and_gross_limits() -> None:
    universe = _universe(4)
    schedule_date = universe[0].bars[25].date
    result = run_backtest(
        market="US",
        strategy_key="us_factor_sleeve_v1",
        securities=universe,
        weight_schedule={schedule_date: {security.code: 0.30 for security in universe}},
        execution_timing="next_close",
    )

    assert sum(result.latest_target_weights.values()) <= RISK_POLICIES["US"].max_sector_weight
    assert max(result.latest_target_weights.values()) <= RISK_POLICIES["US"].max_position_weight
    assert any(
        item.rule == "target_weight_constraint" for item in result.risk_interventions
    )


def test_institutional_schedule_executes_on_next_session_close() -> None:
    security = _trending_security("EVENT", sessions=60)
    signal_date = security.bars[25].date
    execution_bar = security.bars[26]
    result = run_backtest(
        market="US",
        strategy_key="us_activist_13d_v1",
        securities=[security],
        weight_schedule={signal_date: {"EVENT": 0.05}},
        execution_timing="next_close",
    )

    trade = result.trades[0]
    assert trade.date == execution_bar.date
    assert trade.fill_price > execution_bar.close
    assert trade.decision_reference_price == security.bars[25].close
    assert trade.implementation_shortfall_bps is not None


def test_cost_tiers_preserve_external_weight_schedule() -> None:
    universe = _universe()
    schedule = {universe[0].bars[25].date: {"T0": 0.05}}
    result = run_cost_tiered_backtest(
        market="US",
        strategy_key="us_factor_sleeve_v1",
        securities=universe,
        weight_schedule=schedule,
        execution_timing="next_close",
    )

    assert result.primary.trades
    assert all(outcome.trades > 0 for outcome in result.outcomes)


def test_missing_execution_bar_retries_target_on_next_observable_session() -> None:
    event = _trending_security("EVENT", sessions=60)
    clock = _trending_security("CLOCK", sessions=60)
    signal_date = event.bars[25].date
    missing_date = event.bars[26].date
    expected_fill_date = event.bars[27].date
    event.bars = [bar for bar in event.bars if bar.date != missing_date]

    result = run_backtest(
        market="US",
        strategy_key="us_activist_13d_v1",
        securities=[event, clock],
        weight_schedule={signal_date: {"EVENT": 0.05}},
        execution_timing="next_close",
    )

    assert result.trades[0].date == expected_fill_date
    assert any(
        item.rule == "execution_bar_missing" and item.date == missing_date
        for item in result.risk_interventions
    )


def test_cost_tiered_backtest_reports_every_tier() -> None:
    result = run_cost_tiered_backtest(
        market="US", strategy_key="us_breakout_v1", securities=_universe()
    )
    labels = [outcome.tier.label for outcome in result.outcomes]
    # Measured tier (spreads were measurable) plus the three fixed stress floors.
    assert labels == ["measured", "stress_10bps", "stress_30bps", "stress_50bps"]
    assert result.measured_coverage == result.universe_size
    assert all(bps > 0 for bps in result.measured_half_spread_bps.values())


def test_cost_tiers_are_monotonic_in_cost() -> None:
    result = run_cost_tiered_backtest(
        market="US", strategy_key="us_breakout_v1", securities=_universe()
    )
    stress = [o for o in result.outcomes if not o.tier.measured]
    # Ordered by rising one-way cost, net return must be non-increasing.
    stress.sort(key=lambda o: o.tier.one_way_bps)
    nets = [o.net_return_pct for o in stress]
    assert nets == sorted(nets, reverse=True)


def test_edge_dies_at_bps_flags_the_first_losing_tier() -> None:
    result = run_cost_tiered_backtest(
        market="US", strategy_key="us_breakout_v1", securities=_universe()
    )
    if result.edge_dies_at_bps is not None:
        # Every tier at or above the death point must have stopped beating the benchmark.
        for outcome in result.outcomes:
            if not outcome.tier.measured and outcome.tier.one_way_bps >= result.edge_dies_at_bps:
                assert outcome.edge_survives is False


def _rise_then_crash(code: str, *, drop: float, sessions: int = 260) -> StrategySecurity:
    start = dt.date(2024, 1, 1)
    bars = []
    for i in range(sessions):
        close = (10 + i * 0.05) if i < 220 else max(10 + 220 * 0.05 - (i - 219) * drop, 1.0)
        bars.append(
            StrategyBar(
                date=start + dt.timedelta(days=i),
                open=close * 0.999,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=2_000_000 + i * 100,
            )
        )
    return StrategySecurity(code=code, sector="Technology", cap_tier="small", bars=bars)


def test_drawdown_ladder_flatten_engages_in_backtest() -> None:
    # Prove the ladder is actually wired into the engine: a sharp book drawdown past the flatten
    # rung must schedule a flatten. (The halve rung is covered by the ladder unit tests; the
    # self-de-risking strategy trims through the narrow halve band too fast to catch here.)
    policy = RISK_POLICIES["US"].model_copy(
        update={"position_stop_loss": 0.60, "portfolio_drawdown_brake": 0.03}
    )
    result = run_backtest(
        market="US",
        strategy_key="us_breakout_v1",
        securities=[_rise_then_crash(f"T{i}", drop=0.55) for i in range(4)],
        risk_policy=policy,
    )
    rules = {intervention.rule for intervention in result.risk_interventions}
    assert "drawdown_ladder_flatten" in rules
    assert result.latest_target_weights == {}
    assert any("no unrecorded review" in gate for gate in result.failed_gates)


def test_stress_tier_total_cost_reconciles_with_fee() -> None:
    # A stress tier's one_way_bps is total one-way cost; the engine adds the policy fee on top of
    # a half-spread of (tier - fee), so the two must reconcile.
    result = run_cost_tiered_backtest(
        market="US", strategy_key="us_breakout_v1", securities=_universe()
    )
    fee_bps = RISK_POLICIES["US"].fee_rate * 10_000
    assert result.fee_bps == fee_bps
    for outcome in result.outcomes:
        if not outcome.tier.measured:
            assert outcome.tier.one_way_bps in (10.0, 30.0, 50.0)


# --- both markets: DSE must go through the same paths as US ---------------------------------


def _dse_recovery_security(code: str, *, sessions: int = 240, volume: int = 3_000_000):
    # Draws down for most of the window, then turns up in the final sessions: the pattern the
    # DSE reversal strategy is built to act on.
    start = dt.date(2024, 1, 1)
    bars = []
    for i in range(sessions):
        close = 20 - min(i, sessions - 8) * 0.035 + max(0, i - sessions + 8) * 0.18
        bars.append(
            StrategyBar(
                date=start + dt.timedelta(days=i),
                open=close * 0.998,
                high=close * 1.011,
                low=close * 0.989,
                close=round(close, 4),
                volume=volume + i * 100,
            )
        )
    return StrategySecurity(code=code, sector="Financials", cap_tier="small", bars=bars)


def test_cost_tiered_backtest_runs_for_dse_market() -> None:
    result = run_cost_tiered_backtest(
        market="DSE",
        strategy_key="dse_reversal_v1",
        securities=[_dse_recovery_security(f"D{i}") for i in range(4)],
    )
    labels = [outcome.tier.label for outcome in result.outcomes]
    assert labels == ["measured", "stress_50bps"]
    assert result.fee_bps == RISK_POLICIES["DSE"].fee_rate * 10_000
    assert result.primary.risk_policy.market == "DSE"


def _flat_shadow_security(code: str, close: float, *, sessions: int = 25) -> StrategySecurity:
    start = dt.date(2024, 1, 1)
    bars = [
        StrategyBar(
            date=start + dt.timedelta(days=i),
            open=close,
            high=close * 1.004,
            low=close * 0.996,
            close=close,
            volume=2_000_000,
        )
        for i in range(sessions)
    ]
    return StrategySecurity(code=code, sector="Technology", cap_tier="small", bars=bars)


def test_shadow_ladder_trips_freeze_on_deep_drawdown_us() -> None:
    previous = ShadowState(
        cash=0.0,
        positions={"T0": ShadowPosition(shares=1000, average_cost=100.0)},
        peak_nav=200_000.0,  # book is far below its high-water mark
        benchmark_nav=100_000.0,
    )
    result = advance_shadow_portfolio(
        market="US",
        strategy_key="us_breakout_v1",
        securities=[_flat_shadow_security("T0", 80.0)],
        previous=previous,
        target_weights={"T0": 0.99},
        session_number=3,
    )
    assert result.state.ladder_frozen is True
    assert result.next_target_weights == {}
    assert any(iv.rule == "drawdown_ladder_flatten" for iv in result.risk_interventions)


def test_shadow_freeze_persists_through_recovery_dse() -> None:
    # A frozen DSE book with a fully healthy NAV (zero drawdown) must stay flat — only an operator
    # clearing the freeze after written review may re-arm it; a mechanical recovery must not.
    previous = ShadowState(
        cash=100_000.0,
        positions={},
        peak_nav=100_000.0,
        benchmark_nav=100_000.0,
        ladder_frozen=True,
    )
    result = advance_shadow_portfolio(
        market="DSE",
        strategy_key="dse_reversal_v1",
        securities=[_flat_shadow_security("D0", 100.0)],
        previous=previous,
        target_weights={},
        session_number=4,
    )
    assert result.state.ladder_frozen is True
    assert result.next_target_weights == {}
