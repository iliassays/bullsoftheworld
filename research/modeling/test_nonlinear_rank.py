from __future__ import annotations

import datetime as dt

import numpy as np
import polars as pl
import pytest

from research.modeling.nonlinear_rank import (
    RANK_FEATURE_COLUMNS,
    LightGBMRankSpec,
    attach_benchmark_regimes,
    attach_rank_scores,
    fit_lambdarank,
    prepare_ranking_matrix,
)


def _panel(*, dates: int, names: int = 60, seed: int = 17) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for day in range(dates):
        raw = rng.normal(size=(names, len(RANK_FEATURE_COLUMNS)))
        ranked = np.argsort(np.argsort(raw, axis=0), axis=0) / (names - 1) - 0.5
        target = (
            0.04 * ((ranked[:, 0] > 0.1) & (ranked[:, 1] > 0.1))
            + 0.01 * ranked[:, 2]
            + rng.normal(scale=0.003, size=names)
        )
        date = dt.date(2020, 1, 1) + dt.timedelta(days=day)
        for index in range(names):
            row: dict[str, object] = {
                "date": date,
                "code": f"S{index:03d}",
                "net_excess": float(target[index]),
            }
            row.update(
                {
                    feature: float(ranked[index, column])
                    for column, feature in enumerate(RANK_FEATURE_COLUMNS)
                }
            )
            rows.append(row)
    return pl.DataFrame(rows)


def test_relevance_and_weights_are_local_to_each_date() -> None:
    frame = _panel(dates=2, names=20).with_columns(
        pl.when(pl.col("date") == pl.col("date").min())
        .then(pl.col("net_excess") * 1_000.0)
        .otherwise(pl.col("net_excess"))
        .alias("net_excess")
    )

    matrix = prepare_ranking_matrix(frame)

    assert matrix.groups == (20, 20)
    assert len(matrix.labels) == 40
    assert set(matrix.labels[:20]) == set(range(10))
    assert set(matrix.labels[20:]) == set(range(10))
    assert np.isclose(matrix.weights[:20].sum(), 1.0)
    assert np.isclose(matrix.weights[20:].sum(), 1.0)


def test_frozen_spec_hash_changes_with_model_contract() -> None:
    baseline = LightGBMRankSpec()
    edited = LightGBMRankSpec(num_leaves=15)

    assert baseline.spec_hash() == LightGBMRankSpec().spec_hash()
    assert baseline.spec_hash() != edited.spec_hash()


def test_legacy_panel_receives_a_complete_point_in_time_regime_join() -> None:
    date = dt.date(2024, 1, 5)
    panel = pl.DataFrame({"date": [date], "code": ["AAA"]})
    calendar = pl.DataFrame(
        {
            "date": [date],
            "benchmark_trend_regime": ["risk_on"],
            "benchmark_volatility_regime": ["normal"],
        }
    )

    joined = attach_benchmark_regimes(panel, calendar)

    assert joined["benchmark_trend_regime"].to_list() == ["risk_on"]
    with pytest.raises(RuntimeError, match="unavailable"):
        attach_benchmark_regimes(
            panel,
            calendar.filter(pl.col("date") != date),
        )


def test_lambdarank_learns_a_planted_nonlinear_ordering() -> None:
    discovery = _panel(dates=20, seed=3)
    validation = _panel(dates=6, seed=5)
    spec = LightGBMRankSpec(
        min_data_in_leaf=20,
        max_rounds=80,
        early_stopping_rounds=10,
        num_threads=1,
    )

    fitted = fit_lambdarank(discovery, validation, spec=spec)
    scored = attach_rank_scores(
        validation,
        fitted.selection_model,
        num_iteration=fitted.best_iteration,
    )
    prediction_rank = scored["nonlinear_rank_score"].rank().to_numpy()
    target_rank = scored["net_excess"].rank().to_numpy()

    assert 1 <= fitted.best_iteration <= spec.max_rounds
    assert float(np.corrcoef(prediction_rank, target_rank)[0, 1]) > 0.35
