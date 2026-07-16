import datetime as dt

from bulls.analytics.dse_edge_backtest import (
    evaluate_signal,
    promotion_decision,
    simulate_portfolio,
    split_outcomes,
    summarize_outcomes,
)
from bulls.analytics.dse_edges import (
    SPECS,
    EdgeBar,
    ExecutionPolicy,
    generate_signals,
)


def _bars(*, volume_on_reclaim: int = 400_000) -> list[EdgeBar]:
    start = dt.date(2025, 1, 1)
    bars = []
    for index in range(160):
        close = 100 - index * 0.65
        if index >= 83:
            close = 43 + (index - 83) * 0.8
        bars.append(
            EdgeBar(
                date=start + dt.timedelta(days=index),
                open=close * 0.99,
                high=close * 1.01,
                low=close * 0.98,
                close=close,
                volume=200_000,
            )
        )
    reclaim = bars[88]
    bars[88] = EdgeBar(
        date=reclaim.date,
        open=48,
        high=51,
        low=47,
        close=50.5,
        volume=volume_on_reclaim,
    )
    bars[89] = EdgeBar(
        date=bars[89].date,
        open=52,
        high=64,
        low=51,
        close=62,
        volume=300_000,
    )
    return bars


def _market(bars: list[EdgeBar]) -> dict[dt.date, float]:
    return {bar.date: 5_000 + index for index, bar in enumerate(bars)}


def test_deep_reclaim_signal_is_close_confirmed_and_enters_next_session() -> None:
    bars = _bars()
    signals = generate_signals(
        by_code={"EDGE": bars},
        market_closes=_market(bars),
        spec=SPECS["deep_reclaim"],
    )

    assert signals
    assert signals[-1].signal_date == bars[88].date
    assert signals[-1].entry_date == bars[89].date


def test_signal_evaluation_charges_costs_and_uses_next_open() -> None:
    bars = _bars()
    policy = ExecutionPolicy(maximum_adv_participation=0.10)
    signal = generate_signals(
        by_code={"EDGE": bars},
        market_closes=_market(bars),
        spec=SPECS["deep_reclaim"],
        policy=policy,
    )[-1]

    outcome = evaluate_signal(
        signal=signal,
        bars=bars,
        market_closes=_market(bars),
        spec=SPECS["deep_reclaim"],
        policy=policy,
    )

    assert outcome is not None
    assert outcome.entry_date == bars[89].date
    assert outcome.entry_fill > bars[89].open
    assert outcome.net_return_pct < (outcome.exit_fill / outcome.entry_fill - 1) * 100


def test_limit_locked_next_session_is_not_fabricated_as_a_fill() -> None:
    bars = _bars()
    signal = generate_signals(
        by_code={"EDGE": bars},
        market_closes=_market(bars),
        spec=SPECS["deep_reclaim"],
    )[-1]
    previous_close = bars[88].close
    locked = EdgeBar(
        date=bars[89].date,
        open=previous_close * 1.08,
        high=previous_close * 1.08,
        low=previous_close * 1.08,
        close=previous_close * 1.08,
        volume=500_000,
    )
    bars[89] = locked

    assert (
        evaluate_signal(
            signal=signal,
            bars=bars,
            market_closes=_market(bars),
            spec=SPECS["deep_reclaim"],
        )
        is None
    )


def test_split_embargo_keeps_cross_boundary_outcome_out_of_train() -> None:
    bars = _bars()
    policy = ExecutionPolicy(maximum_adv_participation=0.10)
    signal = generate_signals(
        by_code={"EDGE": bars},
        market_closes=_market(bars),
        spec=SPECS["deep_reclaim"],
        policy=policy,
    )[-1]
    outcome = evaluate_signal(
        signal=signal,
        bars=bars,
        market_closes=_market(bars),
        spec=SPECS["deep_reclaim"],
        policy=policy,
    )
    assert outcome is not None

    split = split_outcomes(
        [outcome],
        train_end=outcome.signal_date + dt.timedelta(days=1),
        validation_end=outcome.exit_date + dt.timedelta(days=1),
    )

    assert split["train"] == []
    assert split["validation"] == []


def test_promotion_rejects_small_or_negative_holdouts() -> None:
    empty = summarize_outcomes([])
    decision = promotion_decision(
        base_splits={"train": empty, "validation": empty, "test": empty},
        stressed_splits={"train": empty, "validation": empty, "test": empty},
    )

    assert not decision.eligible_for_forward_paper
    assert any("fewer than 15" in gate for gate in decision.failed_gates)


def test_portfolio_uses_integer_shares_and_reports_costed_return() -> None:
    bars = _bars()
    policy = ExecutionPolicy(maximum_adv_participation=0.10)
    signal = generate_signals(
        by_code={"EDGE": bars},
        market_closes=_market(bars),
        spec=SPECS["deep_reclaim"],
        policy=policy,
    )[-1]
    outcome = evaluate_signal(
        signal=signal,
        bars=bars,
        market_closes=_market(bars),
        spec=SPECS["deep_reclaim"],
        policy=policy,
    )
    assert outcome is not None

    portfolio = simulate_portfolio(
        signals=[signal],
        valid_outcomes=[outcome],
        by_code={"EDGE": bars},
        market_closes=_market(bars),
        spec=SPECS["deep_reclaim"],
        policy=policy,
    )

    assert portfolio.trades == 1
    assert portfolio.fees_paid > 0
    assert portfolio.total_return_pct > 0
