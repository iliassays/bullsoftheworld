from __future__ import annotations

import datetime as dt

import numpy as np
import polars as pl

from research.modeling.cross_sectional_rank import build_benchmark_calendar
from research.modeling.segmented_challenger import (
    DEFAULT_LIQUIDITY_SLEEVES,
    PortfolioConstructionSpec,
    bounded_inverse_volatility_weights,
    evaluate_constructed_book,
    filter_liquidity_sleeve,
)


def _benchmark(periods: int = 320) -> pl.DataFrame:
    dates = [dt.date(2020, 1, 1) + dt.timedelta(days=index) for index in range(periods)]
    close = np.asarray([100.0 * 1.001**index for index in range(periods)])
    return pl.DataFrame(
        {
            "date": dates,
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "adjusted_close": close,
        }
    )


def test_benchmark_regime_is_causal_and_known_at_signal_close() -> None:
    original = _benchmark()
    changed = original.with_columns(
        pl.when(pl.int_range(pl.len()) > 280)
        .then(pl.col("adjusted_close") * 0.2)
        .otherwise(pl.col("adjusted_close"))
        .alias("adjusted_close")
    )
    first = build_benchmark_calendar(original, horizons=(5,))
    second = build_benchmark_calendar(changed, horizons=(5,))
    cutoff = original["date"][260]
    first_row = first.filter(pl.col("date") == cutoff).row(0, named=True)
    second_row = second.filter(pl.col("date") == cutoff).row(0, named=True)

    assert first_row["benchmark_trend_regime"] == "risk_on"
    assert first_row["benchmark_trend_regime"] == second_row["benchmark_trend_regime"]
    assert first_row["benchmark_volatility_20"] == second_row["benchmark_volatility_20"]


def test_liquidity_sleeves_are_non_overlapping_and_regime_gated() -> None:
    rows = []
    date = dt.date(2026, 1, 5)
    for prefix, adv, price in (
        ("D", 60_000_000.0, 10.0),
        ("I", 20_000_000.0, 5.0),
        ("S", 7_000_000.0, 3.0),
    ):
        for index in range(60):
            rows.append(
                {
                    "date": date,
                    "code": f"{prefix}{index}",
                    "close": price,
                    "adv_20": adv,
                    "benchmark_trend_regime": "risk_on",
                    "benchmark_volatility_regime": "normal",
                }
            )
    frame = pl.DataFrame(rows)
    memberships = [
        set(filter_liquidity_sleeve(frame, sleeve)["code"].to_list())
        for sleeve in DEFAULT_LIQUIDITY_SLEEVES
    ]

    assert [len(values) for values in memberships] == [60, 60, 60]
    assert not memberships[0].intersection(memberships[1])
    assert not memberships[1].intersection(memberships[2])
    risk_off = frame.with_columns(benchmark_trend_regime=pl.lit("risk_off"))
    assert all(
        filter_liquidity_sleeve(risk_off, sleeve).is_empty()
        for sleeve in DEFAULT_LIQUIDITY_SLEEVES
    )


def test_bounded_inverse_volatility_weights_respect_capacity() -> None:
    weights = bounded_inverse_volatility_weights(
        np.asarray([0.10, 0.20, 0.40]),
        np.asarray([0.60, 0.40, 0.40]),
    )

    assert weights is not None
    assert abs(float(weights.sum()) - 1.0) < 1e-9
    assert np.all(weights <= np.asarray([0.60, 0.40, 0.40]) + 1e-12)
    assert weights[0] > weights[1] > weights[2]
    assert bounded_inverse_volatility_weights(
        np.asarray([0.10, 0.20, 0.40]),
        np.asarray([0.20, 0.20, 0.20]),
    ) is None


def test_constructed_book_invests_selectively_and_records_abstention() -> None:
    rows = []
    for day in range(3):
        date = dt.date(2025, 1, 6) + dt.timedelta(days=7 * day)
        for index in range(10):
            score = 0.01 - index / 10_000
            if day == 2:
                score = -0.01
            rows.append(
                {
                    "date": date,
                    "code": f"S{index}",
                    "adv_20": 20_000_000.0,
                    "volatility_20": 0.01 + index / 1_000,
                    "model_score": score,
                    "net_excess": 0.01,
                    "stressed_net_excess": 0.008,
                    "gross_excess": 0.012,
                }
            )
    result = evaluate_constructed_book(
        pl.DataFrame(rows),
        score_column="model_score",
        horizon=5,
        construction=PortfolioConstructionSpec(
            book_notional=1_000_000.0,
            max_positions=10,
            minimum_positions=8,
        ),
    )

    assert result["dates"] == 3
    assert result["invested_dates"] == 2
    assert result["trades"] == 20
    assert result["mean_net_pct"] == 1.0
    assert result["abstentions"] == {"insufficient_positive_scores": 1}
    assert result["mean_effective_positions"] >= 8.0
