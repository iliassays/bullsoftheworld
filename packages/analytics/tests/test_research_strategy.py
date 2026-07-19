import datetime as dt

import pytest

from bulls.analytics.research_strategy import (
    CashSettlement,
    SecurityCategoryObservation,
    ShadowPosition,
    ShadowState,
    StrategyBar,
    StrategySecurity,
    advance_shadow_portfolio,
    evaluate_shadow_promotion,
    methodology_boundary_accounting_events,
    opening_accounting_events,
    replay_accounting_events,
    run_backtest,
    settlement_terms_for_security,
)


def _security(
    code: str,
    *,
    market: str,
    sessions: int = 240,
    volume: int = 1_000_000,
    category: str | None = "A",
    category_observations: list[SecurityCategoryObservation] | None = None,
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
    observations = category_observations
    if observations is None and market == "DSE" and category is not None:
        observations = [
            SecurityCategoryObservation(
                category=category,
                known_at=dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
                source="test_fixture",
            )
        ]
    return StrategySecurity(
        code=code,
        sector="Technology",
        cap_tier="small",
        category_observations=observations or [],
        bars=bars,
    )


def test_strategy_cannot_cross_market_policy_boundary() -> None:
    with pytest.raises(ValueError, match="not registered for DSE"):
        run_backtest(
            market="DSE",
            strategy_key="us_breakout_v1",
            securities=[_security("A", market="DSE")],
        )


def test_unknown_strategy_fails_closed() -> None:
    with pytest.raises(ValueError, match="Unknown registered strategy"):
        run_backtest(
            market="US",
            strategy_key="unowned_strategy",
            securities=[_security("A", market="US")],
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


def test_dse_sale_proceeds_do_not_fund_buys_before_t_plus_two_settlement() -> None:
    securities = [
        _security("AAA", market="DSE", sessions=220),
        _security("ZZZ", market="DSE", sessions=220),
    ]
    previous = ShadowState(
        cash=0,
        positions={"ZZZ": ShadowPosition(shares=1_000, average_cost=10)},
        peak_nav=20_000,
        benchmark_nav=20_000,
    )

    first = advance_shadow_portfolio(
        market="DSE",
        strategy_key="dse_reversal_v1",
        securities=securities,
        previous=previous,
        target_weights={"AAA": 0.5},
        session_number=1,
    )

    assert [trade.side for trade in first.trades] == ["sell"]
    assert first.state.cash == 0
    assert first.state.pending_settlements[0].release_session == 3
    assert first.gross_exposure_pct == 0
    assert any(
        item.rule == "cash_limit" and item.code == "AAA" for item in first.risk_interventions
    )

    second = advance_shadow_portfolio(
        market="DSE",
        strategy_key="dse_reversal_v1",
        securities=securities,
        previous=first.state,
        target_weights={"AAA": 0.5},
        session_number=2,
    )
    assert not second.trades
    assert second.state.pending_settlements

    third = advance_shadow_portfolio(
        market="DSE",
        strategy_key="dse_reversal_v1",
        securities=securities,
        previous=second.state,
        target_weights={"AAA": 0.5},
        session_number=3,
    )
    assert any(trade.side == "buy" and trade.code == "AAA" for trade in third.trades)


def test_dse_contractual_settlement_uses_point_in_time_category_and_market_sessions() -> None:
    trade_date = dt.date(2026, 7, 16)  # Thursday; DSE's next session is Sunday.
    category_history = [
        SecurityCategoryObservation(
            category="A",
            known_at=dt.datetime(2026, 7, 10, tzinfo=dt.UTC),
            source="dse_company_page",
        ),
        SecurityCategoryObservation(
            category="Z",
            known_at=dt.datetime(2026, 7, 15, tzinfo=dt.UTC),
            source="dse_company_page",
        ),
    ]
    security = _security(
        "CATEGORY",
        market="DSE",
        category_observations=category_history,
    )

    z_terms = settlement_terms_for_security(
        market="DSE",
        security=security,
        trade_date=trade_date,
    )
    a_terms = settlement_terms_for_security(
        market="DSE",
        security=security,
        trade_date=dt.date(2026, 7, 14),
    )

    assert z_terms.security_category == "Z"
    assert z_terms.settlement_sessions == 3
    assert z_terms.contractual_settlement_date == dt.date(2026, 7, 21)
    assert a_terms.security_category == "A"
    assert a_terms.settlement_sessions == 2
    assert a_terms.contractual_settlement_date == dt.date(2026, 7, 16)


def test_dse_order_fails_closed_without_category_known_before_market_open() -> None:
    security = _security("UNKNOWN", market="DSE", category=None)
    advanced = advance_shadow_portfolio(
        market="DSE",
        strategy_key="dse_reversal_v1",
        securities=[security],
        previous=ShadowState(
            cash=100_000,
            positions={},
            peak_nav=100_000,
            benchmark_nav=100_000,
        ),
        target_weights={"UNKNOWN": 0.1},
        session_number=1,
    )

    assert advanced.trades == []
    assert any(
        item.rule == "settlement_class_unsupported" and item.code == "UNKNOWN"
        for item in advanced.risk_interventions
    )


def test_dse_order_fails_closed_on_conflicting_category_observations() -> None:
    known_at = dt.datetime(2025, 6, 15, tzinfo=dt.UTC)
    security = _security(
        "CONFLICT",
        market="DSE",
        category_observations=[
            SecurityCategoryObservation(
                category="A",
                known_at=known_at,
                source="source_a",
            ),
            SecurityCategoryObservation(
                category="Z",
                known_at=known_at,
                source="source_b",
            ),
        ],
    )
    advanced = advance_shadow_portfolio(
        market="DSE",
        strategy_key="dse_reversal_v1",
        securities=[security],
        previous=ShadowState(
            cash=100_000,
            positions={},
            peak_nav=100_000,
            benchmark_nav=100_000,
        ),
        target_weights={"CONFLICT": 0.1},
        session_number=1,
    )

    assert advanced.trades == []
    assert any(
        item.rule == "settlement_class_unsupported" and "conflicting" in item.detail
        for item in advanced.risk_interventions
    )


def test_dse_bought_shares_cannot_be_sold_before_contractual_settlement() -> None:
    security = _security("LOCKED", market="DSE", sessions=220)
    initial = ShadowState(
        cash=100_000,
        positions={},
        peak_nav=100_000,
        benchmark_nav=100_000,
    )
    first = advance_shadow_portfolio(
        market="DSE",
        strategy_key="dse_reversal_v1",
        securities=[security],
        previous=initial,
        target_weights={"LOCKED": 0.1},
        session_number=1,
    )
    second = advance_shadow_portfolio(
        market="DSE",
        strategy_key="dse_reversal_v1",
        securities=[security],
        previous=first.state,
        target_weights={},
        session_number=2,
    )
    third = advance_shadow_portfolio(
        market="DSE",
        strategy_key="dse_reversal_v1",
        securities=[security],
        previous=second.state,
        target_weights={},
        session_number=3,
    )

    assert first.state.pending_share_settlements
    assert second.trades == []
    assert any(item.rule == "share_settlement_lock" for item in second.risk_interventions)
    assert any(trade.side == "sell" for trade in third.trades)


def test_stale_held_bar_does_not_freeze_due_settlement_release() -> None:
    stale = _security("STALE", market="DSE", sessions=219)
    current = _security("CURRENT", market="DSE", sessions=220)
    as_of_date = current.bars[-1].date
    receivable = CashSettlement(
        receivable_key="s1:receivable:SOLD",
        release_session=2,
        amount=5_000,
        trade_date=stale.bars[-1].date,
        contractual_settlement_date=as_of_date,
        settlement_sessions=2,
        settlement_rule="bsec-z-category-directive-2024-07-02",
        settlement_class="dse_abgn_regular",
        trade_type="regular",
        security_category="A",
    )
    advanced = advance_shadow_portfolio(
        market="DSE",
        strategy_key="dse_reversal_v1",
        securities=[stale, current],
        previous=ShadowState(
            cash=10_000,
            positions={"STALE": ShadowPosition(shares=100, average_cost=10)},
            pending_settlements=[receivable],
            peak_nav=20_000,
            benchmark_nav=20_000,
        ),
        target_weights={"STALE": 0.1},
        session_number=2,
        as_of_date=as_of_date,
    )

    assert advanced.state.cash == 15_000
    assert advanced.state.pending_settlements == []
    assert advanced.trades == []
    assert any(item.rule == "stale_mark" for item in advanced.risk_interventions)


def test_us_sale_proceeds_release_after_one_completed_session() -> None:
    securities = [
        _security("AAA", market="US", sessions=220),
        _security("ZZZ", market="US", sessions=220),
    ]
    previous = ShadowState(
        cash=0,
        positions={"ZZZ": ShadowPosition(shares=1_000, average_cost=10)},
        peak_nav=20_000,
        benchmark_nav=20_000,
    )

    first = advance_shadow_portfolio(
        market="US",
        strategy_key="us_breakout_v1",
        securities=securities,
        previous=previous,
        target_weights={"AAA": 0.5},
        session_number=1,
    )
    assert [trade.side for trade in first.trades] == ["sell"]
    assert first.state.pending_settlements[0].release_session == 2

    second = advance_shadow_portfolio(
        market="US",
        strategy_key="us_breakout_v1",
        securities=securities,
        previous=first.state,
        target_weights={"AAA": 0.5},
        session_number=2,
    )
    assert not second.state.pending_settlements
    assert any(trade.side == "buy" and trade.code == "AAA" for trade in second.trades)


def test_cash_is_allocated_across_the_complete_buy_basket_without_ticker_bias() -> None:
    securities = [
        _security("AAA", market="US", sessions=220),
        _security("BBB", market="US", sessions=220),
    ]
    advanced = advance_shadow_portfolio(
        market="US",
        strategy_key="us_breakout_v1",
        securities=securities,
        previous=ShadowState(
            cash=1_000,
            positions={},
            peak_nav=1_000,
            benchmark_nav=1_000,
        ),
        target_weights={"AAA": 0.8, "BBB": 0.8},
        session_number=1,
    )

    quantities = {trade.code: trade.quantity for trade in advanced.trades}
    assert set(quantities) == {"AAA", "BBB"}
    assert abs(quantities["AAA"] - quantities["BBB"]) <= 1
    assert all("cash_capacity" in trade.constraint_notes for trade in advanced.trades)

    reversed_input = advance_shadow_portfolio(
        market="US",
        strategy_key="us_breakout_v1",
        securities=list(reversed(securities)),
        previous=ShadowState(
            cash=1_000,
            positions={},
            peak_nav=1_000,
            benchmark_nav=1_000,
        ),
        target_weights={"BBB": 0.8, "AAA": 0.8},
        session_number=1,
    )
    assert reversed_input.state == advanced.state
    assert reversed_input.trades == advanced.trades


def test_missing_target_bar_is_an_explicit_rejection() -> None:
    advanced = advance_shadow_portfolio(
        market="US",
        strategy_key="us_breakout_v1",
        securities=[_security("VISIBLE", market="US", sessions=220)],
        previous=ShadowState(
            cash=100_000,
            positions={},
            peak_nav=100_000,
            benchmark_nav=100_000,
        ),
        target_weights={"MISSING": 0.1},
        session_number=1,
    )

    assert advanced.trades == []
    assert any(
        item.rule == "missing_bar" and item.code == "MISSING"
        for item in advanced.risk_interventions
    )


def test_missing_held_security_stops_shadow_advancement() -> None:
    with pytest.raises(ValueError, match=r"cannot advance without current history.*HELD"):
        advance_shadow_portfolio(
            market="DSE",
            strategy_key="dse_reversal_v1",
            securities=[_security("VISIBLE", market="DSE", sessions=220)],
            previous=ShadowState(
                cash=10_000,
                positions={"HELD": ShadowPosition(shares=100, average_cost=10)},
                peak_nav=20_000,
                benchmark_nav=20_000,
            ),
            target_weights={},
            session_number=1,
        )


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


def test_new_shadow_book_opens_from_accounting_events_not_a_snapshot() -> None:
    effective_date = dt.date(2026, 7, 18)
    events = opening_accounting_events(
        initial_capital=100_000,
        effective_date=effective_date,
    )

    replayed = replay_accounting_events(None, events)

    assert [event.event_key for event in events] == ["s0:opening_balance"]
    assert replayed == ShadowState(
        cash=100_000,
        positions={},
        peak_nav=100_000,
        benchmark_nav=100_000,
    )


def test_accounting_ledger_replays_dse_fills_receivable_and_t_plus_two_release() -> None:
    securities = [
        _security("AAA", market="DSE", sessions=220),
        _security("ZZZ", market="DSE", sessions=220),
    ]
    initial = ShadowState(
        cash=0,
        positions={"ZZZ": ShadowPosition(shares=1_000, average_cost=10)},
        peak_nav=20_000,
        benchmark_nav=20_000,
    )
    boundary = methodology_boundary_accounting_events(
        state=initial,
        session_number=0,
        effective_date=securities[0].bars[-2].date,
        source_snapshot_id="legacy-snapshot",
    )
    first = advance_shadow_portfolio(
        market="DSE",
        strategy_key="dse_reversal_v1",
        securities=securities,
        previous=initial,
        target_weights={"AAA": 0.5},
        session_number=1,
    )
    second = advance_shadow_portfolio(
        market="DSE",
        strategy_key="dse_reversal_v1",
        securities=securities,
        previous=first.state,
        target_weights={"AAA": 0.5},
        session_number=2,
    )
    third = advance_shadow_portfolio(
        market="DSE",
        strategy_key="dse_reversal_v1",
        securities=securities,
        previous=second.state,
        target_weights={"AAA": 0.5},
        session_number=3,
    )

    assert replay_accounting_events(initial, first.accounting_events) == first.state
    assert replay_accounting_events(first.state, second.accounting_events) == second.state
    assert replay_accounting_events(second.state, third.accounting_events) == third.state
    assert any(
        event.event_type == "fill" and event.payload["settlement"]["release_session"] == 3
        for event in first.accounting_events
    )
    assert not any(event.event_type == "settlement_release" for event in second.accounting_events)
    assert any(event.event_type == "settlement_release" for event in third.accounting_events)
    assert (
        replay_accounting_events(
            None,
            boundary + first.accounting_events + second.accounting_events + third.accounting_events,
        )
        == third.state
    )


def test_accounting_event_keys_and_payloads_are_deterministic_on_retry() -> None:
    security = _security("FLOW", market="US", sessions=220)
    previous = ShadowState(
        cash=100_000,
        positions={},
        peak_nav=100_000,
        benchmark_nav=100_000,
    )

    first = advance_shadow_portfolio(
        market="US",
        strategy_key="us_breakout_v1",
        securities=[security],
        previous=previous,
        target_weights={"FLOW": 0.1},
        session_number=1,
    )
    retry = advance_shadow_portfolio(
        market="US",
        strategy_key="us_breakout_v1",
        securities=[security],
        previous=previous,
        target_weights={"FLOW": 0.1},
        session_number=1,
    )

    assert [event.model_dump(mode="json") for event in first.accounting_events] == [
        event.model_dump(mode="json") for event in retry.accounting_events
    ]
