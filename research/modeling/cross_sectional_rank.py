"""Causal cross-sectional return-ranking model for Atlas research.

The module deliberately contains no database or execution code.  It accepts completed daily
bars, constructs features using observations available at the signal close, labels outcomes from
the next session's open, fits an auditable ridge model, and evaluates a capital-constrained top-k
book after explicit costs.

Historical U.S. experiments currently use today's active security master because complete
delisted/listing history only began in July 2026.  Callers must therefore label their result as a
survivor-only diagnostic upper bound; this module cannot promote a strategy.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import polars as pl

FEATURE_COLUMNS = (
    "residual_return_5",
    "residual_return_20",
    "residual_return_60",
    "residual_return_120",
    "distance_sma_20",
    "distance_sma_50",
    "distance_sma_200",
    "volatility_20",
    "volatility_60",
    "relative_volume_1_20",
    "relative_volume_5_20",
    "log_adv_20",
    "position_52w",
    "drawdown_60",
    "atr_14_pct",
    "overnight_gap",
)


@dataclass(frozen=True, slots=True)
class CrossSectionalSpec:
    """Frozen model and execution contract; change ``version`` when any field changes."""

    key: str = "us_eod_cross_sectional_rank"
    version: str = "v1"
    market: str = "US"
    horizon: int = 5
    minimum_history: int = 252
    minimum_price: float = 2.0
    minimum_adv: float = 5_000_000.0
    positions_per_rebalance: int = 10
    discovery_end: dt.date = dt.date(2022, 12, 31)
    validation_end: dt.date = dt.date(2024, 12, 31)
    ridge_penalties: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0)
    data_scope: str = "current_survivors_diagnostic_upper_bound"

    def spec_hash(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class RidgeModel:
    """Small serializable ridge regressor over cross-sectional percentile features."""

    feature_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    intercept: float
    penalty: float

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        if matrix.ndim != 2 or matrix.shape[1] != len(self.feature_names):
            raise ValueError("matrix shape does not match model features")
        return self.intercept + matrix @ np.asarray(self.coefficients)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rolling_mean(column: str, window: int) -> pl.Expr:
    return pl.col(column).rolling_mean(window, min_samples=window)


def _rolling_std(column: str, window: int) -> pl.Expr:
    return pl.col(column).rolling_std(window, min_samples=window)


def _round_trip_cost(adv_column: str = "adv_20") -> pl.Expr:
    """Conservative U.S. round-trip implementation cost by trailing dollar liquidity."""

    adv = pl.col(adv_column)
    return (
        pl.when(adv >= 50_000_000)
        .then(0.0010)
        .when(adv >= 10_000_000)
        .then(0.0020)
        .when(adv >= 5_000_000)
        .then(0.0030)
        .when(adv >= 1_000_000)
        .then(0.0050)
        .otherwise(0.0100)
    )


def build_benchmark_calendar(
    bars: pl.DataFrame,
    *,
    horizons: Iterable[int] = (5, 20),
) -> pl.DataFrame:
    """Create the SPY calendar, lagged benchmark features and next-open outcomes."""

    required = {"date", "open", "high", "low", "close", "adjusted_close"}
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"Missing benchmark columns: {sorted(missing)}")

    frame = (
        bars.sort("date")
        .filter(
            (pl.col("open") > 0)
            & (pl.col("close") > 0)
            & (pl.col("adjusted_close") > 0)
        )
        .with_row_index("session_ordinal")
        .with_columns(adjustment=pl.col("adjusted_close") / pl.col("close"))
        .with_columns(adjusted_open=pl.col("open") * pl.col("adjustment"))
    )

    expressions: list[pl.Expr] = []
    for lookback in (5, 20, 60, 120):
        expressions.append(
            (pl.col("adjusted_close") / pl.col("adjusted_close").shift(lookback) - 1.0).alias(
                f"benchmark_return_{lookback}"
            )
        )
    for horizon in horizons:
        expressions.extend(
            (
                (
                    pl.col("adjusted_close").shift(-horizon)
                    / pl.col("adjusted_open").shift(-1)
                    - 1.0
                ).alias(f"benchmark_fwd_{horizon}"),
                pl.col("date").shift(-horizon).alias(f"benchmark_exit_date_{horizon}"),
            )
        )
    return frame.with_columns(expressions).select(
        "date",
        "session_ordinal",
        *(f"benchmark_return_{lookback}" for lookback in (5, 20, 60, 120)),
        *(item for horizon in horizons for item in (f"benchmark_fwd_{horizon}", f"benchmark_exit_date_{horizon}")),
    )


def build_symbol_observations(
    bars: pl.DataFrame,
    benchmark_calendar: pl.DataFrame,
    spec: CrossSectionalSpec,
) -> pl.DataFrame:
    """Build sampled, causal observations for one symbol.

    The signal is measured at session ``t`` and the return begins at adjusted open ``t+1``.
    ``session_ordinal % horizon`` creates non-overlapping rebalance cohorts for the primary
    evaluation and keeps every symbol aligned to the same market calendar.
    """

    required = {
        "code",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "adjusted_close",
    }
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"Missing symbol bar columns: {sorted(missing)}")
    if bars.is_empty():
        return pl.DataFrame()
    if bars["code"].n_unique() != 1:
        raise ValueError("build_symbol_observations accepts exactly one symbol")

    horizon = spec.horizon
    frame = (
        bars.sort("date")
        .filter(
            (pl.col("open") > 0)
            & (pl.col("high") > 0)
            & (pl.col("low") > 0)
            & (pl.col("close") > 0)
            & (pl.col("adjusted_close") > 0)
        )
        .with_row_index("bars_seen")
        .with_columns(
            adjustment=pl.col("adjusted_close") / pl.col("close"),
            turnover=pl.col("close") * pl.col("volume").cast(pl.Float64),
        )
        .with_columns(
            adjusted_open=pl.col("open") * pl.col("adjustment"),
            adjusted_high=pl.col("high") * pl.col("adjustment"),
            adjusted_low=pl.col("low") * pl.col("adjustment"),
            return_1=pl.col("adjusted_close") / pl.col("adjusted_close").shift(1) - 1.0,
        )
        .with_columns(
            sma_20=_rolling_mean("adjusted_close", 20),
            sma_50=_rolling_mean("adjusted_close", 50),
            sma_200=_rolling_mean("adjusted_close", 200),
            avg_volume_5=_rolling_mean("volume", 5),
            avg_volume_20=_rolling_mean("volume", 20),
            adv_20=_rolling_mean("turnover", 20),
            high_60=pl.col("adjusted_high").rolling_max(60, min_samples=60),
            high_252=pl.col("adjusted_high").rolling_max(252, min_samples=252),
            low_252=pl.col("adjusted_low").rolling_min(252, min_samples=252),
        )
        .with_columns(
            volatility_20=_rolling_std("return_1", 20),
            volatility_60=_rolling_std("return_1", 60),
            true_range=pl.max_horizontal(
                pl.col("adjusted_high") - pl.col("adjusted_low"),
                (pl.col("adjusted_high") - pl.col("adjusted_close").shift(1)).abs(),
                (pl.col("adjusted_low") - pl.col("adjusted_close").shift(1)).abs(),
            ),
        )
        .with_columns(atr_14=_rolling_mean("true_range", 14))
        .join(benchmark_calendar, on="date", how="inner")
    )

    features: list[pl.Expr] = []
    for lookback in (5, 20, 60, 120):
        features.append(
            (
                pl.col("adjusted_close") / pl.col("adjusted_close").shift(lookback)
                - 1.0
                - pl.col(f"benchmark_return_{lookback}")
            ).alias(f"residual_return_{lookback}")
        )

    frame = frame.with_columns(
        *features,
        distance_sma_20=pl.col("adjusted_close") / pl.col("sma_20") - 1.0,
        distance_sma_50=pl.col("adjusted_close") / pl.col("sma_50") - 1.0,
        distance_sma_200=pl.col("adjusted_close") / pl.col("sma_200") - 1.0,
        relative_volume_1_20=pl.col("volume") / pl.col("avg_volume_20") - 1.0,
        relative_volume_5_20=pl.col("avg_volume_5") / pl.col("avg_volume_20") - 1.0,
        log_adv_20=pl.col("adv_20").log1p(),
        position_52w=(pl.col("adjusted_close") - pl.col("low_252"))
        / (pl.col("high_252") - pl.col("low_252")),
        drawdown_60=pl.col("adjusted_close") / pl.col("high_60") - 1.0,
        atr_14_pct=pl.col("atr_14") / pl.col("adjusted_close"),
        overnight_gap=pl.col("adjusted_open") / pl.col("adjusted_close").shift(1) - 1.0,
        gross_return=(
            pl.col("adjusted_close").shift(-horizon)
            / pl.col("adjusted_open").shift(-1)
            - 1.0
        ),
        exit_date=pl.col("date").shift(-horizon),
        cost=_round_trip_cost(),
    ).with_columns(
        gross_excess=pl.col("gross_return") - pl.col(f"benchmark_fwd_{horizon}"),
        net_excess=(
            pl.col("gross_return")
            - pl.col(f"benchmark_fwd_{horizon}")
            - pl.col("cost")
        ),
        stressed_net_excess=(
            pl.col("gross_return")
            - pl.col(f"benchmark_fwd_{horizon}")
            - 2.0 * pl.col("cost")
        ),
    )

    finite = pl.all_horizontal(*(pl.col(name).is_finite() for name in FEATURE_COLUMNS))
    return frame.filter(
        (pl.col("session_ordinal") % horizon == 0)
        & (pl.col("bars_seen") >= spec.minimum_history)
        & (pl.col("close") >= spec.minimum_price)
        & (pl.col("adv_20") >= spec.minimum_adv)
        & (pl.col("volume") > 0)
        & pl.col("net_excess").is_finite()
        & pl.col("exit_date").is_not_null()
        & finite
    ).select(
        "date",
        "exit_date",
        "session_ordinal",
        "code",
        "close",
        "adv_20",
        "gross_return",
        f"benchmark_fwd_{horizon}",
        "gross_excess",
        "cost",
        "net_excess",
        "stressed_net_excess",
        *FEATURE_COLUMNS,
    )


def rank_features(frame: pl.DataFrame) -> pl.DataFrame:
    """Convert each feature to a same-date percentile in ``[-0.5, 0.5]``."""

    if frame.is_empty():
        return frame
    count = pl.len().over("date")
    expressions = []
    for name in FEATURE_COLUMNS:
        rank = pl.col(name).rank(method="average").over("date")
        expressions.append(
            pl.when(count > 1)
            .then((rank - 1.0) / (count - 1.0) - 0.5)
            .otherwise(0.0)
            .alias(f"x_{name}")
        )
    return frame.with_columns(expressions)


def temporal_window(frame: pl.DataFrame, spec: CrossSectionalSpec, name: str) -> pl.DataFrame:
    """Return a purged chronological window using the realised exit date."""

    if name == "discovery":
        return frame.filter(pl.col("exit_date") <= spec.discovery_end)
    if name == "validation":
        return frame.filter(
            (pl.col("date") > spec.discovery_end)
            & (pl.col("exit_date") <= spec.validation_end)
        )
    if name == "holdout":
        return frame.filter(pl.col("date") > spec.validation_end)
    raise ValueError(f"Unknown temporal window: {name}")


def fit_ridge(
    frame: pl.DataFrame,
    *,
    penalty: float,
    target: str = "net_excess",
) -> RidgeModel:
    """Fit a date-balanced ridge model using sufficient statistics only."""

    if penalty < 0:
        raise ValueError("penalty must be non-negative")
    feature_names = tuple(f"x_{name}" for name in FEATURE_COLUMNS)
    clean = frame.drop_nulls([*feature_names, target])
    if clean.height <= len(feature_names):
        raise ValueError("not enough observations to fit the model")

    # Winsorisation is learned independently within each historical date and only protects the
    # fit from bad prints; evaluation always uses the original realised return.
    clean = clean.with_columns(
        pl.col(target)
        .clip(
            pl.col(target).quantile(0.005).over("date"),
            pl.col(target).quantile(0.995).over("date"),
        )
        .alias("_fit_target"),
        (1.0 / pl.len().over("date")).alias("_date_weight"),
    )
    matrix = clean.select(feature_names).to_numpy()
    response = clean["_fit_target"].to_numpy()
    weights = clean["_date_weight"].to_numpy()
    weights = weights / weights.sum()

    x_mean = np.average(matrix, axis=0, weights=weights)
    y_mean = float(np.average(response, weights=weights))
    centered_x = matrix - x_mean
    centered_y = response - y_mean
    xtwx = centered_x.T @ (centered_x * weights[:, None])
    xtwy = centered_x.T @ (centered_y * weights)
    coefficients = np.linalg.solve(
        xtwx + penalty * np.eye(len(feature_names)),
        xtwy,
    )
    intercept = y_mean - float(x_mean @ coefficients)
    return RidgeModel(
        feature_names=feature_names,
        coefficients=tuple(float(value) for value in coefficients),
        intercept=intercept,
        penalty=penalty,
    )


def attach_scores(
    frame: pl.DataFrame,
    model: RidgeModel,
    *,
    score_column: str = "model_score",
) -> pl.DataFrame:
    matrix = frame.select(model.feature_names).to_numpy()
    return frame.with_columns(pl.Series(score_column, model.predict(matrix)))


def _drawdown(returns: np.ndarray) -> float | None:
    if returns.size == 0:
        return None
    equity = np.cumprod(1.0 + returns)
    peaks = np.maximum.accumulate(equity)
    return float(np.min(equity / peaks - 1.0))


def evaluate_top_book(
    frame: pl.DataFrame,
    *,
    score_column: str,
    horizon: int,
    positions: int,
) -> dict[str, Any]:
    """Evaluate an equal-weight top-k book on non-overlapping rebalance dates."""

    if positions < 1:
        raise ValueError("positions must be positive")
    clean = frame.drop_nulls([score_column, "net_excess", "stressed_net_excess"])
    if clean.is_empty():
        return {"dates": 0, "trades": 0}
    selected = (
        clean.sort(["date", score_column, "code"], descending=[False, True, False])
        .with_columns(pl.int_range(pl.len()).over("date").alias("_selection_rank"))
        .filter(pl.col("_selection_rank") < positions)
    )
    per_date = (
        selected.group_by("date")
        .agg(
            net=pl.col("net_excess").mean(),
            stressed=pl.col("stressed_net_excess").mean(),
            gross=pl.col("gross_excess").mean(),
        )
        .sort("date")
    )
    returns = per_date["net"].to_numpy()
    stressed = per_date["stressed"].to_numpy()
    periods_per_year = 252.0 / horizon
    standard_deviation = float(np.std(returns, ddof=1)) if returns.size > 1 else 0.0
    sharpe = (
        float(np.mean(returns) / standard_deviation * math.sqrt(periods_per_year))
        if standard_deviation > 0
        else None
    )
    return {
        "dates": per_date.height,
        "trades": selected.height,
        "symbols": selected["code"].n_unique(),
        "mean_net_pct": float(np.mean(returns) * 100.0),
        "mean_stressed_pct": float(np.mean(stressed) * 100.0),
        "annualized_net_pct": float(np.mean(returns) * periods_per_year * 100.0),
        "hit_rate_pct": float(np.mean(returns > 0) * 100.0),
        "sharpe": sharpe,
        "maximum_drawdown_pct": (
            _drawdown(returns) * 100.0 if _drawdown(returns) is not None else None
        ),
    }


def evaluate_ranking(
    frame: pl.DataFrame,
    *,
    score_column: str,
    horizon: int,
    positions: int,
) -> dict[str, Any]:
    """Return rank information coefficient, decile spread and top-book diagnostics."""

    clean = frame.drop_nulls([score_column, "net_excess"])
    if clean.is_empty():
        return {"rows": 0, "dates": 0}
    ranked = clean.with_columns(
        pl.col(score_column).rank(method="average").over("date").alias("_score_rank"),
        pl.col("net_excess").rank(method="average").over("date").alias("_target_rank"),
    )
    per_date_ic = (
        ranked.group_by("date")
        .agg(pl.corr("_score_rank", "_target_rank").alias("ic"))
        .drop_nulls("ic")
    )
    deciles = (
        ranked.with_columns(
            (
                pl.col("_score_rank") * 10.0 / (pl.len().over("date") + 1.0)
            )
            .floor()
            .clip(0, 9)
            .cast(pl.Int8)
            .alias("score_decile")
        )
        .group_by("score_decile")
        .agg(mean_net_pct=pl.col("net_excess").mean() * 100.0, rows=pl.len())
        .sort("score_decile")
        .to_dicts()
    )
    ic_values = per_date_ic["ic"].to_numpy()
    return {
        "rows": clean.height,
        "dates": clean["date"].n_unique(),
        "mean_daily_rank_ic": float(np.mean(ic_values)) if ic_values.size else None,
        "median_daily_rank_ic": float(np.median(ic_values)) if ic_values.size else None,
        "positive_ic_dates_pct": (
            float(np.mean(ic_values > 0) * 100.0) if ic_values.size else None
        ),
        "deciles": deciles,
        "top_book": evaluate_top_book(
            ranked,
            score_column=score_column,
            horizon=horizon,
            positions=positions,
        ),
    }


def finite_dict(value: Any) -> Any:
    """Convert NumPy values and non-finite floats into strict JSON-compatible values."""

    if isinstance(value, dict):
        return {key: finite_dict(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_dict(item) for item in value]
    if isinstance(value, np.generic):
        return finite_dict(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
