import datetime as dt

import pytest

from bulls.analytics.research_strategy import (
    EquityPoint,
    ShadowPosition,
    ShadowState,
    StrategyBar,
    StrategySecurity,
    advance_shadow_portfolio,
    evaluate_shadow_promotion,
    robustness_slices,
    run_backtest,
)


def _security(
    code: str,
    *,
    market: str,
    sessions: int = 240,
    volume: int = 1_000_000,
) -> StrategySecurity:
    start = dt.date(2025, 1, 1)
    bars = []
    for index in range(sessions):
        # US data trends; DSE data draws down and then turns during the final week.
        if market == "US":
            close = 10 + index * 0.03
        else:
            close = 20 - min(index, sessions - 8) * 0.035 + max(0, index - sessions + 8) * 0.18
        bars.append(
            StrategyBar(
                date=start + dt.timedelta(days=index),
                open=close * 0.998,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=volume + index * 100,
            )
        )
    return StrategySecurity(code=code, sector="Technology", cap_tier="small", bars=bars)


def test_strategy_cannot_cross_market_policy_boundary() -> None:
    with pytest.raises(ValueError, match="not registered for DSE"):
        run_backtest(
            market="DSE",
            strategy_key="us_breakout_v1",
            securities=[_security("A", market="DSE")],
        )


def test_us_backtest_uses_next_session_and_charges_costs() -> None:
    securities = [_security(f"T{index}", market="US") for index in range(4)]
    result = run_backtest(
        market="US",
        strategy_key="us_breakout_v1",
        securities=securities,
    )

    assert result.trades
    first_trade = result.trades[0]
    # First signal can only exist after 200 completed observations and fills the following session.
    assert first_trade.date > securities[0].bars[200].date
    assert result.fees_paid > 0
    assert max(result.latest_target_weights.values(), default=0) <= 0.10
    assert result.validation_status == "diagnostic"
    assert "Inactive and delisted security history is not complete." in result.failed_gates
    assert (
        "Point-in-time input revisions are not complete for the test window." in result.failed_gates
    )


def test_unknown_adv_rejects_orders_instead_of_fabricating_liquidity() -> None:
    securities = [_security("ZERO", market="US", volume=0)]
    result = run_backtest(
        market="US",
        strategy_key="us_breakout_v1",
        securities=securities,
    )

    assert result.trades == []


def test_empty_history_degrades_to_diagnostic_result() -> None:
    result = run_backtest(
        market="US",
        strategy_key="us_breakout_v1",
        securities=[],
    )

    assert result.final_nav == 100_000
    assert result.equity_curve == []
    assert result.validation_status == "diagnostic"


def test_shadow_book_executes_prior_close_target_at_current_open() -> None:
    security = _security("FLOW", market="US", sessions=220)
    previous = ShadowState(
        cash=100_000,
        positions={},
        peak_nav=100_000,
        benchmark_nav=100_000,
    )

    advanced = advance_shadow_portfolio(
        market="US",
        strategy_key="us_breakout_v1",
        securities=[security],
        previous=previous,
        target_weights={"FLOW": 0.1},
        session_number=1,
    )

    assert advanced.date == security.bars[-1].date
    assert advanced.trades[0].date == security.bars[-1].date
    assert advanced.trades[0].fill_price > security.bars[-1].open
    assert advanced.state.cumulative_fees > 0
    assert advanced.state.positions["FLOW"].shares > 0


def test_institutional_shadow_uses_close_and_external_next_target() -> None:
    security = _security("FLOW", market="US", sessions=220)
    previous = ShadowState(
        cash=100_000,
        positions={},
        peak_nav=100_000,
        benchmark_nav=100_000,
    )

    advanced = advance_shadow_portfolio(
        market="US",
        strategy_key="us_factor_sleeve_v1",
        securities=[security],
        previous=previous,
        target_weights={"FLOW": 0.05},
        next_target_weights={"FLOW": 0.02},
        execution_timing="next_close",
        session_number=1,
    )

    assert advanced.trades[0].fill_price > security.bars[-1].close
    assert advanced.trades[0].reason.endswith("(next-close)")
    assert advanced.trades[0].decision_reference_price == security.bars[-2].close
    assert advanced.trades[0].implementation_shortfall_bps is not None
    assert advanced.next_target_weights == {"FLOW": 0.02}


def test_named_regime_slices_use_only_observed_points() -> None:
    points = [
        {
            "date": dt.date(2020, 2, 3),
            "nav": 100.0,
            "benchmark": 100.0,
            "cash": 100.0,
            "gross_exposure_pct": 0.0,
            "drawdown_pct": 0.0,
        },
        {
            "date": dt.date(2020, 3, 3),
            "nav": 80.0,
            "benchmark": 90.0,
            "cash": 80.0,
            "gross_exposure_pct": 0.0,
            "drawdown_pct": 20.0,
        },
        {
            "date": dt.date(2021, 12, 30),
            "nav": 120.0,
            "benchmark": 110.0,
            "cash": 120.0,
            "gross_exposure_pct": 0.0,
            "drawdown_pct": 0.0,
        },
    ]
    curve = [EquityPoint.model_validate(point) for point in points]

    slices = robustness_slices(curve)

    assert [item.key for item in slices] == ["pandemic_dislocation_2020_2021"]
    assert slices[0].sessions == 3
    assert slices[0].total_return_pct == 20.0
    assert slices[0].benchmark_return_pct == 10.0
    assert slices[0].max_drawdown_pct == 20.0


def test_shadow_book_stop_schedules_next_open_exit_without_hindsight_fill() -> None:
    security = _security("RISK", market="US", sessions=220)
    previous = ShadowState(
        cash=50_000,
        positions={"RISK": ShadowPosition(shares=1_000, average_cost=25)},
        peak_nav=100_000,
        benchmark_nav=100_000,
    )

    advanced = advance_shadow_portfolio(
        market="US",
        strategy_key="us_breakout_v1",
        securities=[security],
        previous=previous,
        target_weights={"RISK": 0.1},
        session_number=1,
    )

    assert "RISK" not in advanced.next_target_weights
    assert any(item.rule == "position_stop" for item in advanced.risk_interventions)
    sell = next(trade for trade in advanced.trades if trade.side == "sell")
    assert sell.decision_reference_price is not None
    expected_shortfall = round(
        (1 - sell.fill_price / sell.decision_reference_price) * 10_000,
        3,
    )
    assert sell.implementation_shortfall_bps == pytest.approx(expected_shortfall, abs=0.1)


def test_backtest_carries_last_mark_when_held_security_bar_is_missing() -> None:
    securities = [_security(f"M{index}", market="US") for index in range(4)]
    missing_date = securities[3].bars[220].date
    securities[3].bars = [bar for bar in securities[3].bars if bar.date != missing_date]

    result = run_backtest(
        market="US",
        strategy_key="us_breakout_v1",
        securities=securities,
    )

    stale = [
        item
        for item in result.risk_interventions
        if item.rule == "stale_mark" and item.date == missing_date
    ]
    assert stale
    point = next(item for item in result.equity_curve if item.date == missing_date)
    assert point.drawdown_pct < 5


def test_diagnostic_source_can_never_be_promoted_by_forward_performance() -> None:
    decision = evaluate_shadow_promotion(
        source_validation_status="diagnostic",
        initial_nav=100_000,
        latest_nav=140_000,
        initial_benchmark_nav=100_000,
        latest_benchmark_nav=105_000,
        sessions=120,
        maximum_drawdown_pct=4,
        executions=80,
    )

    assert decision.status == "diagnostic"
    assert not next(
        check for check in decision.checks if check.key == "historical_validation"
    ).passed


def test_shadow_promotion_requires_forward_window_and_all_risk_gates() -> None:
    collecting = evaluate_shadow_promotion(
        source_validation_status="eligible_for_shadow",
        initial_nav=100_000,
        latest_nav=104_000,
        initial_benchmark_nav=100_000,
        latest_benchmark_nav=101_000,
        sessions=40,
        maximum_drawdown_pct=8,
        executions=12,
    )
    eligible = evaluate_shadow_promotion(
        source_validation_status="eligible_for_shadow",
        initial_nav=100_000,
        latest_nav=108_000,
        initial_benchmark_nav=100_000,
        latest_benchmark_nav=103_000,
        sessions=65,
        maximum_drawdown_pct=9,
        executions=22,
    )
    rejected = evaluate_shadow_promotion(
        source_validation_status="eligible_for_shadow",
        initial_nav=100_000,
        latest_nav=95_000,
        initial_benchmark_nav=100_000,
        latest_benchmark_nav=103_000,
        sessions=65,
        maximum_drawdown_pct=18,
        executions=22,
    )

    assert collecting.status == "collecting"
    assert eligible.status == "eligible"
    assert rejected.status == "rejected"
