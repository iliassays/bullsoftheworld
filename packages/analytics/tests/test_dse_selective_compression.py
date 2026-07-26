from __future__ import annotations

import datetime as dt

import pytest

from bulls.analytics.dse_selective_compression import (
    SelectiveCompressionFeatures,
    SelectiveCompressionObservation,
    SelectiveCompressionPolicy,
    build_selective_compression_schedule,
    build_selective_features,
    evaluate_selective_compression_admission,
)
from bulls.analytics.research_strategy import (
    EquityPoint,
    StrategyBar,
    _desired_shares_with_rebalance_band,
)


def _bars(count: int = 80) -> list[StrategyBar]:
    start = dt.date(2026, 1, 1)
    return [
        StrategyBar(
            date=start + dt.timedelta(days=index),
            open=100 + index * 0.2,
            high=102 + index * 0.2,
            low=99 + index * 0.2,
            close=101 + index * 0.2,
            volume=100_000 if index < count - 1 else 220_000,
        )
        for index in range(count)
    ]


def _features() -> SelectiveCompressionFeatures:
    return SelectiveCompressionFeatures(
        relative_strength_63=0.08,
        relative_volume_20=2.2,
        base_volume_contraction=0.75,
        cmf_20=0.12,
        obv_flow_20=0.20,
        close_location=0.85,
        extension_from_trigger_pct=0.01,
        extension_atr=0.40,
        stop_distance_pct=0.06,
        stock_above_sma_50=True,
        benchmark_above_sma_50=True,
    )


def _confirmation(
    code: str,
    date: dt.date,
    *,
    features: SelectiveCompressionFeatures | None = None,
    liquidity: float = 20,
) -> SelectiveCompressionObservation:
    return SelectiveCompressionObservation(
        code=code,
        as_of_date=date,
        state="confirmed",
        previous_state="trigger_ready",
        evidence_mode="forward",
        methodology_version="squeeze-monitor-v3",
        setup_price=100,
        trigger_price=102,
        invalidation_price=96,
        risk_per_share=6,
        average_daily_value_mn=liquidity,
        features=features or _features(),
    )


def test_feature_snapshot_does_not_read_future_bars() -> None:
    bars = _bars()
    as_of = bars[-2].date
    benchmark = [(bar.date, 100 + index * 0.1) for index, bar in enumerate(bars)]

    before_future_spike = build_selective_features(
        bars=bars,
        benchmark_closes=benchmark,
        as_of=as_of,
        trigger_price=bars[-2].close - 1,
        invalidation_price=bars[-2].close - 8,
    )
    mutated = bars.copy()
    mutated[-1] = mutated[-1].model_copy(update={"close": 1_000, "volume": 100_000_000})
    after_future_spike = build_selective_features(
        bars=mutated,
        benchmark_closes=benchmark,
        as_of=as_of,
        trigger_price=bars[-2].close - 1,
        invalidation_price=bars[-2].close - 8,
    )

    assert before_future_spike == after_future_spike


def test_relative_strength_aligns_benchmark_to_stock_reference_date() -> None:
    bars = _bars()
    benchmark = [(bars[index].date, 100 + index) for index in [*range(63), len(bars) - 1]]

    features = build_selective_features(
        bars=bars,
        benchmark_closes=benchmark,
        as_of=bars[-1].date,
        trigger_price=bars[-1].close - 1,
        invalidation_price=bars[-1].close - 8,
    )

    assert features is not None
    stock_return = bars[-1].close / bars[-64].close - 1
    benchmark_return = benchmark[-1][1] / benchmark[16][1] - 1
    assert features.relative_strength_63 == pytest.approx(stock_return - benchmark_return)


def test_selective_schedule_ranks_and_limits_positions() -> None:
    sessions = [dt.date(2026, 1, 1) + dt.timedelta(days=index) for index in range(90)]
    date = sessions[70]
    strongest = _features().model_copy(update={"relative_strength_63": 0.18})
    middle = _features().model_copy(update={"relative_strength_63": 0.10})
    weakest = _features().model_copy(update={"relative_strength_63": 0.03})
    rejected = _features().model_copy(update={"cmf_20": -0.10})

    built = build_selective_compression_schedule(
        observations=[
            _confirmation("WEAK", date, features=weakest),
            _confirmation("BEST", date, features=strongest),
            _confirmation("MID", date, features=middle),
            _confirmation("NOFLOW", date, features=rejected),
        ],
        sessions=sessions,
        policy=SelectiveCompressionPolicy(maximum_positions=2, maximum_gross_weight=0.20),
        evidence_mode="forward",
    )

    assert set(built.target_weights[date]) == {"BEST", "MID"}
    assert built.confirmations == 4
    assert built.quality_qualified == 3
    assert built.accepted_entries == 2
    assert {item.reason for item in built.rejections} == {"cmf_distribution", "position_limit"}


def test_selective_schedule_refuses_reconstructed_and_pre_registration_rows() -> None:
    sessions = [dt.date(2026, 1, 1) + dt.timedelta(days=index) for index in range(90)]
    registration = sessions[70]
    old = _confirmation("OLD", sessions[69])
    reconstructed = _confirmation("REPLAY", sessions[71]).model_copy(
        update={"evidence_mode": "reconstructed"}
    )
    live = _confirmation("LIVE", sessions[72])

    built = build_selective_compression_schedule(
        observations=[old, reconstructed, live],
        sessions=sessions,
        evidence_mode="forward",
        signal_not_before=registration,
    )

    assert built.target_weights == {sessions[72]: {"LIVE": 0.08333333}}


def test_rebalance_band_suppresses_churn_but_not_entries_or_exits() -> None:
    assert (
        _desired_shares_with_rebalance_band(
            current_shares=100,
            desired_shares=110,
            target_weight=0.10,
            band_pct=0.20,
        )
        == 100
    )
    assert (
        _desired_shares_with_rebalance_band(
            current_shares=100,
            desired_shares=140,
            target_weight=0.10,
            band_pct=0.20,
        )
        == 140
    )
    assert (
        _desired_shares_with_rebalance_band(
            current_shares=0,
            desired_shares=100,
            target_weight=0.10,
            band_pct=0.20,
        )
        == 100
    )
    assert (
        _desired_shares_with_rebalance_band(
            current_shares=100,
            desired_shares=0,
            target_weight=0.0,
            band_pct=0.20,
        )
        == 0
    )


def _equity_curve(*, weak_test: bool = False) -> list[EquityPoint]:
    start = dt.date(2025, 1, 1)
    points: list[EquityPoint] = []
    nav = 10_000_000.0
    benchmark = 10_000_000.0
    for index in range(180):
        strategy_return = 0.0008
        if weak_test and index >= 144:
            strategy_return = -0.001
        if index:
            nav *= 1 + strategy_return
            benchmark *= 1.0003
        points.append(
            EquityPoint(
                date=start + dt.timedelta(days=index),
                nav=nav,
                benchmark=benchmark,
                cash=5_000_000,
                gross_exposure_pct=30,
                drawdown_pct=0,
            )
        )
    return points


def test_selective_admission_requires_positive_holdout_and_null_models() -> None:
    comparators = {
        "timing": {
            "strategy_beats_realistic": True,
            "strategy_beats_stress_30bps": True,
        },
        "liquidity": {
            "strategy_beats_realistic": True,
            "strategy_beats_stress_30bps": True,
        },
    }
    admitted = evaluate_selective_compression_admission(
        equity_curve=_equity_curve(),
        maximum_drawdown_pct=2.0,
        accepted_entries=15,
        buy_executions=14,
        benchmark_valid=True,
        stress_30bps_return_pct=3.0,
        comparator_summary=comparators,
        deflated_sharpe_summary={"deflated_sharpe": 0.90},
    )
    rejected = evaluate_selective_compression_admission(
        equity_curve=_equity_curve(weak_test=True),
        maximum_drawdown_pct=2.0,
        accepted_entries=15,
        buy_executions=14,
        benchmark_valid=True,
        stress_30bps_return_pct=3.0,
        comparator_summary=comparators,
        deflated_sharpe_summary={"deflated_sharpe": 0.90},
    )

    assert admitted.passed is True
    assert rejected.passed is False
    assert "positive_test_excess_return" in rejected.failed_checks
