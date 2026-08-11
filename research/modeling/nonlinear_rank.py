"""Frozen shallow nonlinear ranker for Atlas's offline U.S. research.

This module contains no database, serving, portfolio-target or execution integration. It turns an
already causal, same-date ranked panel into LightGBM query groups, trains one preregistered
LambdaRank model, and preserves the discovery-only selection model separately from the
discovery-plus-validation forward model.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import polars as pl

from research.modeling.cross_sectional_rank import FEATURE_COLUMNS

RANK_FEATURE_COLUMNS = tuple(f"x_{name}" for name in FEATURE_COLUMNS)


@dataclass(frozen=True, slots=True)
class LightGBMRankSpec:
    """One preregistered low-complexity LambdaRank configuration."""

    key: str = "us_eod_deep_liquidity_lambdarank"
    version: str = "v2"
    market: str = "US"
    horizon: int = 20
    relevance_bins: int = 10
    learning_rate: float = 0.02
    num_leaves: int = 7
    max_depth: int = 3
    min_data_in_leaf: int = 5_000
    feature_fraction: float = 0.8
    bagging_fraction: float = 0.8
    bagging_freq: int = 1
    lambda_l1: float = 0.1
    lambda_l2: float = 10.0
    max_bin: int = 63
    max_rounds: int = 500
    early_stopping_rounds: int = 50
    num_threads: int = 4
    seed: int = 20260811
    unit_row_weights: bool = True
    lambdarank_query_normalization: bool = True
    bagging_by_query: bool = True
    trial_count: int = 2

    def spec_hash(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class RankingMatrix:
    """Contiguous query-group matrix accepted by LightGBM's ranking objective."""

    features: np.ndarray
    labels: np.ndarray
    weights: np.ndarray
    groups: tuple[int, ...]
    dates: tuple[dt.date, ...]
    codes: tuple[str, ...]


@dataclass(slots=True)
class RankerFit:
    """Keep the genuine-validation clock separate from the post-selection refit."""

    selection_model: Any
    forward_model: Any
    best_iteration: int


def _lightgbm():
    try:
        import lightgbm as lgb
    except ImportError as exc:  # pragma: no cover - exercised only without research extras
        raise RuntimeError(
            "LightGBM is required for this offline experiment; run with --group research"
        ) from exc
    return lgb


def _clean_rank_frame(frame: pl.DataFrame, *, target: str) -> pl.DataFrame:
    required = {"date", "code", target, *RANK_FEATURE_COLUMNS}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing rank columns: {sorted(missing)}")
    finite = pl.all_horizontal(
        *(pl.col(name).is_finite() for name in (*RANK_FEATURE_COLUMNS, target))
    )
    return frame.drop_nulls(list(required)).filter(finite).sort(["date", "code"])


def attach_benchmark_regimes(
    panel: pl.DataFrame,
    regime_calendar: pl.DataFrame,
) -> pl.DataFrame:
    """Attach a causal SPY regime to legacy panels and fail closed on missing dates."""

    columns = {"benchmark_trend_regime", "benchmark_volatility_regime"}
    if columns.issubset(panel.columns):
        return panel
    joined = panel.join(regime_calendar, on="date", how="left")
    missing = joined.filter(
        pl.any_horizontal(*(pl.col(name).is_null() for name in columns))
    ).height
    if missing:
        raise RuntimeError(f"SPY regime is unavailable for {missing} panel rows")
    return joined


def prepare_ranking_matrix(
    frame: pl.DataFrame,
    *,
    relevance_bins: int = 10,
    target: str = "net_excess",
    unit_row_weights: bool = True,
) -> RankingMatrix:
    """Create date-local relevance labels and contiguous ranking-query groups."""

    if relevance_bins < 2:
        raise ValueError("relevance_bins must be at least two")
    clean = _clean_rank_frame(frame, target=target)
    if clean.is_empty():
        raise ValueError("ranking matrix cannot be empty")
    count = pl.len().over("date")
    labelled = clean.with_columns(
        (
            ((pl.col(target).rank(method="average").over("date") - 1.0) * relevance_bins / count)
            .floor()
            .clip(0, relevance_bins - 1)
            .cast(pl.Int32)
        ).alias("_relevance"),
        (pl.lit(1.0) if unit_row_weights else 1.0 / count).alias("_row_weight"),
    )
    groups = tuple(
        int(value)
        for value in (
            labelled.group_by("date", maintain_order=True)
            .agg(pl.len().alias("rows"))["rows"]
            .to_list()
        )
    )
    if sum(groups) != labelled.height:
        raise RuntimeError("LightGBM group sizes do not match the ranked panel")
    return RankingMatrix(
        features=labelled.select(RANK_FEATURE_COLUMNS).to_numpy(),
        labels=labelled["_relevance"].to_numpy(),
        weights=labelled["_row_weight"].to_numpy(),
        groups=groups,
        dates=tuple(labelled["date"].to_list()),
        codes=tuple(str(code) for code in labelled["code"].to_list()),
    )


def _parameters(spec: LightGBMRankSpec) -> dict[str, Any]:
    return {
        "objective": "lambdarank",
        "metric": "ndcg",
        "eval_at": [10, 50],
        "lambdarank_truncation_level": 50,
        "lambdarank_norm": spec.lambdarank_query_normalization,
        "learning_rate": spec.learning_rate,
        "num_leaves": spec.num_leaves,
        "max_depth": spec.max_depth,
        "min_data_in_leaf": spec.min_data_in_leaf,
        "feature_fraction": spec.feature_fraction,
        "bagging_fraction": spec.bagging_fraction,
        "bagging_freq": spec.bagging_freq,
        "bagging_by_query": spec.bagging_by_query,
        "lambda_l1": spec.lambda_l1,
        "lambda_l2": spec.lambda_l2,
        "max_bin": spec.max_bin,
        "deterministic": True,
        "force_col_wise": True,
        "seed": spec.seed,
        "feature_fraction_seed": spec.seed,
        "bagging_seed": spec.seed,
        "data_random_seed": spec.seed,
        "num_threads": spec.num_threads,
        "verbosity": -1,
    }


def _dataset(matrix: RankingMatrix):
    lgb = _lightgbm()
    return lgb.Dataset(
        matrix.features,
        label=matrix.labels,
        weight=matrix.weights,
        group=list(matrix.groups),
        feature_name=list(RANK_FEATURE_COLUMNS),
        free_raw_data=False,
    )


def fit_lambdarank(
    discovery: pl.DataFrame,
    validation: pl.DataFrame,
    *,
    spec: LightGBMRankSpec,
) -> RankerFit:
    """Select tree count on validation, then refit once for future-only scoring."""

    if spec.horizon != 20:
        raise ValueError("the preregistered nonlinear challenger is 20-session only")
    lgb = _lightgbm()
    discovery_matrix = prepare_ranking_matrix(
        discovery,
        relevance_bins=spec.relevance_bins,
        unit_row_weights=spec.unit_row_weights,
    )
    validation_matrix = prepare_ranking_matrix(
        validation,
        relevance_bins=spec.relevance_bins,
        unit_row_weights=spec.unit_row_weights,
    )
    selection_model = lgb.train(
        _parameters(spec),
        _dataset(discovery_matrix),
        num_boost_round=spec.max_rounds,
        valid_sets=[_dataset(validation_matrix)],
        valid_names=["validation"],
        callbacks=[
            lgb.early_stopping(spec.early_stopping_rounds, verbose=False),
            lgb.log_evaluation(period=0),
        ],
    )
    best_iteration = int(selection_model.best_iteration or spec.max_rounds)
    pre_forward = pl.concat((discovery, validation), how="vertical_relaxed")
    forward_matrix = prepare_ranking_matrix(
        pre_forward,
        relevance_bins=spec.relevance_bins,
        unit_row_weights=spec.unit_row_weights,
    )
    forward_model = lgb.train(
        _parameters(spec),
        _dataset(forward_matrix),
        num_boost_round=best_iteration,
        callbacks=[lgb.log_evaluation(period=0)],
    )
    return RankerFit(
        selection_model=selection_model,
        forward_model=forward_model,
        best_iteration=best_iteration,
    )


def attach_rank_scores(
    frame: pl.DataFrame,
    model: Any,
    *,
    score_column: str = "nonlinear_rank_score",
    target: str = "net_excess",
    num_iteration: int | None = None,
) -> pl.DataFrame:
    """Score a labelled evaluation frame while preserving its point-in-time columns."""

    clean = _clean_rank_frame(frame, target=target)
    scores = model.predict(
        clean.select(RANK_FEATURE_COLUMNS).to_numpy(),
        num_iteration=num_iteration,
    )
    return clean.with_columns(pl.Series(score_column, np.asarray(scores, dtype=float)))


def top_k_reproducibility(
    first: pl.DataFrame,
    second: pl.DataFrame,
    *,
    score_column: str = "nonlinear_rank_score",
    positions: int = 10,
) -> dict[str, float | int | bool]:
    """Compare decision membership from two fits over identical point-in-time rows."""

    if positions <= 0:
        raise ValueError("positions must be positive")
    required = {"date", "code", score_column}
    if missing := required.difference(first.columns):
        raise ValueError(f"First score frame is missing columns: {sorted(missing)}")
    if missing := required.difference(second.columns):
        raise ValueError(f"Second score frame is missing columns: {sorted(missing)}")
    left = first.select("date", "code", score_column).sort(["date", "code"])
    right = second.select("date", "code", score_column).sort(["date", "code"])
    left_keys = list(zip(left["date"].to_list(), left["code"].to_list(), strict=True))
    right_keys = list(zip(right["date"].to_list(), right["code"].to_list(), strict=True))
    if left_keys != right_keys:
        raise ValueError("score frames do not contain the same date/code observations")

    dates = np.asarray(left["date"].to_list())
    codes = np.asarray(left["code"].to_list(), dtype=str)
    first_scores = left[score_column].to_numpy()
    second_scores = right[score_column].to_numpy()
    absolute_delta = np.abs(first_scores - second_scores)
    unique_dates = np.unique(dates)
    exact_matches = 0
    overlap_rates: list[float] = []
    for date in unique_dates:
        mask = dates == date
        date_codes = codes[mask]
        count = min(positions, len(date_codes))
        first_order = np.lexsort((date_codes, -first_scores[mask]))[:count]
        second_order = np.lexsort((date_codes, -second_scores[mask]))[:count]
        first_members = set(date_codes[first_order])
        second_members = set(date_codes[second_order])
        exact_matches += first_members == second_members
        overlap_rates.append(len(first_members & second_members) / count if count else 1.0)

    evaluated_dates = len(unique_dates)
    return {
        "dates": evaluated_dates,
        "exact_membership_dates": exact_matches,
        "exact_membership_rate_pct": (
            exact_matches / evaluated_dates * 100.0 if evaluated_dates else 100.0
        ),
        "mean_top_k_overlap_pct": (
            float(np.mean(overlap_rates)) * 100.0 if overlap_rates else 100.0
        ),
        "max_absolute_score_delta": (float(absolute_delta.max()) if absolute_delta.size else 0.0),
        "reproducible": exact_matches == evaluated_dates,
    }


def feature_importance(model: Any) -> list[dict[str, float | str]]:
    gains = np.asarray(model.feature_importance(importance_type="gain"), dtype=float)
    total = float(gains.sum())
    rows = [
        {
            "feature": name.removeprefix("x_"),
            "gain": float(gain),
            "gain_pct": float(gain / total * 100.0) if total > 0 else 0.0,
        }
        for name, gain in zip(RANK_FEATURE_COLUMNS, gains, strict=True)
    ]
    return sorted(rows, key=lambda row: float(row["gain"]), reverse=True)


__all__ = [
    "RANK_FEATURE_COLUMNS",
    "LightGBMRankSpec",
    "RankerFit",
    "RankingMatrix",
    "attach_benchmark_regimes",
    "attach_rank_scores",
    "feature_importance",
    "fit_lambdarank",
    "prepare_ranking_matrix",
    "top_k_reproducibility",
]
