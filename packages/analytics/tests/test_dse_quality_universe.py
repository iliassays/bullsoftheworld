import datetime as dt

import pytest

from bulls.analytics.dse_edges import EdgeBar, EdgeSignal, ExecutionPolicy
from bulls.analytics.dse_quality_universe import (
    QualityDividend,
    QualityFinancial,
    QualityUniversePolicy,
    filter_signals_to_quality_universe,
    quality_snapshot_at,
)


def _bars(*, volume: int = 600_000) -> list[EdgeBar]:
    start = dt.date(2025, 1, 1)
    return [
        EdgeBar(
            date=start + dt.timedelta(days=index),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=volume,
        )
        for index in range(180)
    ]


def _financials(current_eps: float = 10) -> dict[str, list[QualityFinancial]]:
    return {
        "QUALITY": [
            QualityFinancial(fiscal_year=2021, eps=8, nav_per_share=45),
            QualityFinancial(fiscal_year=2022, eps=9, nav_per_share=48),
            QualityFinancial(fiscal_year=2023, eps=current_eps, nav_per_share=50),
            QualityFinancial(fiscal_year=2024, eps=100, nav_per_share=100),
        ]
    }


def _dividends() -> dict[str, list[QualityDividend]]:
    return {
        "QUALITY": [
            QualityDividend(year=2021, cash_pct=10),
            QualityDividend(year=2022, cash_pct=10),
            QualityDividend(year=2023, cash_pct=10),
        ]
    }


def test_quality_gate_requires_durability_value_and_full_position_capacity() -> None:
    bars = _bars()
    snapshot = quality_snapshot_at(
        code="QUALITY",
        bars=bars,
        index=150,
        financials=_financials(),
        dividends=_dividends(),
        quality_policy=QualityUniversePolicy(),
        execution_policy=ExecutionPolicy(
            assumed_capital=10_000_000,
            target_position_weight=0.085,
        ),
        next_market_date=bars[151].date,
    )

    assert snapshot.passes
    assert snapshot.fiscal_year == 2023
    assert snapshot.required_trailing_value == pytest.approx(42_500_000)
    assert snapshot.full_target_capacity
    assert snapshot.pe == 10
    assert snapshot.pb == 2
    assert snapshot.roe_pct == 20


def test_quality_gate_rejects_illiquidity_eps_collapse_and_missing_dividends() -> None:
    bars = _bars(volume=10_000)
    snapshot = quality_snapshot_at(
        code="QUALITY",
        bars=bars,
        index=150,
        financials=_financials(current_eps=2),
        dividends={"QUALITY": []},
        quality_policy=QualityUniversePolicy(),
        execution_policy=ExecutionPolicy(
            assumed_capital=10_000_000,
            target_position_weight=0.085,
        ),
        next_market_date=bars[151].date,
    )

    assert not snapshot.passes
    assert "insufficient_liquidity" in snapshot.failures
    assert not snapshot.full_target_capacity
    assert "low_roe" in snapshot.failures
    assert "eps_collapse" in snapshot.failures
    assert "inconsistent_cash_dividend" in snapshot.failures


def test_quality_gate_ignores_financial_years_that_are_not_conservatively_known() -> None:
    bars = _bars()
    snapshot = quality_snapshot_at(
        code="QUALITY",
        bars=bars,
        index=10,
        financials=_financials(),
        dividends=_dividends(),
        quality_policy=QualityUniversePolicy(minimum_history=5),
        execution_policy=ExecutionPolicy(assumed_capital=1_000_000),
    )

    # The signal is in 2025, so FY2024's apparently exceptional EPS must not be visible.
    assert snapshot.fiscal_year == 2023
    assert snapshot.pe == 10


def test_registered_price_signal_is_filtered_before_execution() -> None:
    bars = _bars()
    signal = EdgeSignal(
        strategy="deep_reclaim",
        code="QUALITY",
        signal_index=150,
        signal_date=bars[150].date,
        entry_index=151,
        entry_date=bars[151].date,
        score=1,
        trailing_value=60_000_000,
        evidence=(),
    )
    selected, snapshots = filter_signals_to_quality_universe(
        signals=[signal],
        by_code={"QUALITY": bars},
        market_closes={bar.date: 5_000 for bar in bars},
        financials=_financials(),
        dividends=_dividends(),
        quality_policy=QualityUniversePolicy(),
        execution_policy=ExecutionPolicy(
            assumed_capital=10_000_000,
            target_position_weight=0.085,
        ),
    )

    assert selected == [signal]
    assert snapshots[("QUALITY", bars[150].date)].passes
