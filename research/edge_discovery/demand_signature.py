"""Causal DSE demand-signature experiment.

This module is deliberately research-only. It turns daily OHLCV into testable evidence about
persistent demand and supply contraction; it does not claim to identify institutions, does not
write to production, and cannot create Atlas paper targets.

The contract is strict:

* features use the signal close or older observations only;
* labels enter at the next session's open;
* a stop wins an intraday target/stop tie because daily bars cannot reveal event order;
* model standardisation and coefficients are fitted on discovery data only;
* chronological windows are purged when their outcome crosses a split boundary;
* candidate selection is capital constrained rather than treating every high score as tradable.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import polars as pl

FEATURE_COLUMNS = (
    "cmf_5",
    "cmf_20",
    "cmf_acceleration",
    "obv_pressure_5",
    "obv_pressure_20",
    "obv_acceleration",
    "up_down_volume_asymmetry",
    "down_volume_dryup",
    "absorption",
    "price_impact_efficiency",
    "atr_compression",
    "range_compression",
    "ret_5",
    "ret_20",
    "ret_60",
    "rel_volume_5",
    "rel_volume_20",
    "volume_trend",
    "proximity_high_20",
    "proximity_high_120",
    "higher_low",
    "relative_strength_20",
    "market_regime",
    "flow_x_compression",
    "absorption_x_proximity",
    "demand_x_dryup",
    "rs_x_flow_acceleration",
)


@dataclass(frozen=True)
class DemandSignatureSpec:
    """Frozen experiment specification; change the key when any value changes."""

    key: str = "dse_demand_signature_v1"
    primary_horizon: int = 10
    primary_target: float = 0.15
    primary_stop: float = 0.06
    secondary_horizon: int = 20
    secondary_target: float = 0.20
    secondary_stop: float = 0.08
    minimum_history: int = 60
    minimum_adv_bdt: float = 10_000_000.0
    score_quantile: float = 0.95
    candidates_per_session: int = 3
    portfolio_slots: int = 3
    l2_penalty: float = 4.0
    one_way_cost_bps: float = 100.0
    stressed_one_way_cost_bps: float = 150.0
    suspicious_drop: float = -0.10

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RidgeLogitModel:
    """Small auditable classifier, avoiding an opaque research dependency."""

    feature_names: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    iterations: int
    converged: bool

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        x = (matrix - np.asarray(self.means)) / np.asarray(self.scales)
        logits = self.intercept + x @ np.asarray(self.coefficients)
        logits = np.clip(logits, -35.0, 35.0)
        return 1.0 / (1.0 + np.exp(-logits))

    def coefficient_rows(self) -> list[dict[str, float | str]]:
        return sorted(
            (
                {"feature": name, "coefficient": coefficient}
                for name, coefficient in zip(
                    self.feature_names, self.coefficients, strict=True
                )
            ),
            key=lambda row: abs(float(row["coefficient"])),
            reverse=True,
        )


@dataclass(frozen=True)
class WindowResult:
    window: str
    eligible_rows: int
    selected_events: int
    selected_dates: int
    base_rate: float | None
    precision: float | None
    precision_lift_pp: float | None
    matched_precision_lift_pp: float | None
    mean_gross_return_pct: float | None
    mean_net_return_pct: float | None
    mean_stressed_return_pct: float | None
    matched_excess_net_pct: float | None
    hit_rate_pct: float | None
    median_mfe_pct: float | None
    median_mae_pct: float | None
    net_ci_low_pct: float | None
    net_ci_high_pct: float | None


@dataclass(frozen=True)
class PortfolioResult:
    trades: int
    rejected_for_slots: int
    total_return_pct: float
    benchmark_return_pct: float | None
    excess_return_pct: float | None
    maximum_drawdown_pct: float
    win_rate_pct: float | None


def _safe_ratio(numerator: pl.Expr, denominator: pl.Expr) -> pl.Expr:
    return pl.when(denominator.abs() > 1e-12).then(numerator / denominator).otherwise(None)


def build_features(
    bars: pl.DataFrame,
    *,
    minimum_adv_bdt: float = 10_000_000.0,
    minimum_history: int = 60,
    suspicious_drop: float = -0.10,
) -> pl.DataFrame:
    """Build causal demand/supply trajectory features from sorted daily bars.

    ``benchmark_close`` is optional. When absent, benchmark-relative fields are null and those
    rows cannot enter the model. The production runner always joins DSEX before calling this.
    """
    required = {"code", "date", "open", "high", "low", "close", "volume"}
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"Missing bar columns: {sorted(missing)}")

    frame = bars.sort(["code", "date"])
    if "benchmark_close" not in frame.columns:
        frame = frame.with_columns(pl.lit(None, dtype=pl.Float64).alias("benchmark_close"))

    prev_close = pl.col("close").shift(1).over("code")
    raw_range = pl.col("high") - pl.col("low")
    close_location = _safe_ratio(pl.col("close") - pl.col("low"), raw_range)
    ret_1 = _safe_ratio(pl.col("close"), prev_close) - 1.0
    true_range = pl.max_horizontal(
        raw_range,
        (pl.col("high") - prev_close).abs(),
        (pl.col("low") - prev_close).abs(),
    )

    frame = frame.with_columns(
        bars_seen=pl.col("code").cum_count().over("code"),
        prev_close=prev_close,
        ret_1=ret_1,
        true_range=true_range,
        close_location=close_location,
        close_location_value=(2.0 * close_location - 1.0),
        turnover=pl.col("close") * pl.col("volume").cast(pl.Float64),
    ).with_columns(
        signed_volume=pl.col("close_location_value") * pl.col("volume"),
        obv_step=pl.col("ret_1").sign() * pl.col("volume"),
        down_volume=pl.when(pl.col("ret_1") < 0).then(pl.col("volume")).otherwise(0),
        benchmark_ret_1=(
            pl.col("benchmark_close")
            / pl.col("benchmark_close").shift(1).over("code")
            - 1.0
        ),
        suspicious_feature_drop=(pl.col("ret_1") <= suspicious_drop).cast(pl.Int8),
    )

    for window in (5, 20):
        frame = frame.with_columns(
            **{
                f"volume_sum_{window}": pl.col("volume")
                .rolling_sum(window, min_samples=window)
                .over("code"),
                f"signed_volume_sum_{window}": pl.col("signed_volume")
                .rolling_sum(window, min_samples=window)
                .over("code"),
                f"obv_sum_{window}": pl.col("obv_step")
                .rolling_sum(window, min_samples=window)
                .over("code"),
                f"down_volume_sum_{window}": pl.col("down_volume")
                .rolling_sum(window, min_samples=window)
                .over("code"),
                f"avg_volume_{window}": pl.col("volume")
                .rolling_mean(window, min_samples=window)
                .over("code"),
            }
        )

    frame = frame.with_columns(
        avg_volume_60=pl.col("volume").rolling_mean(60, min_samples=60).over("code"),
        adv_20=pl.col("turnover").rolling_mean(20, min_samples=20).over("code"),
        vol_60=pl.col("ret_1").rolling_std(60, min_samples=40).over("code"),
        atr_5=pl.col("true_range").rolling_mean(5, min_samples=5).over("code"),
        atr_14=pl.col("true_range").rolling_mean(14, min_samples=14).over("code"),
        atr_20=pl.col("true_range").rolling_mean(20, min_samples=20).over("code"),
        high_20=pl.col("high").rolling_max(20, min_samples=20).over("code"),
        high_120=pl.col("high").rolling_max(120, min_samples=60).over("code"),
        low_5=pl.col("low").rolling_min(5, min_samples=5).over("code"),
        low_20=pl.col("low").rolling_min(20, min_samples=20).over("code"),
        ret_5=(pl.col("close") / pl.col("close").shift(5).over("code") - 1.0),
        ret_20=(pl.col("close") / pl.col("close").shift(20).over("code") - 1.0),
        ret_60=(pl.col("close") / pl.col("close").shift(60).over("code") - 1.0),
        benchmark_ret_20=(
            pl.col("benchmark_close")
            / pl.col("benchmark_close").shift(20).over("code")
            - 1.0
        ),
        clean_feature_history=(
            pl.col("suspicious_feature_drop")
            .rolling_sum(60, min_samples=1)
            .over("code")
            == 0
        ),
    )

    cmf_5 = _safe_ratio(pl.col("signed_volume_sum_5"), pl.col("volume_sum_5"))
    cmf_20 = _safe_ratio(pl.col("signed_volume_sum_20"), pl.col("volume_sum_20"))
    obv_5 = _safe_ratio(pl.col("obv_sum_5"), pl.col("volume_sum_5"))
    obv_20 = _safe_ratio(pl.col("obv_sum_20"), pl.col("volume_sum_20"))
    down_pace_5 = pl.col("down_volume_sum_5") / 5.0
    down_pace_20 = pl.col("down_volume_sum_20") / 20.0
    range_pct = _safe_ratio(pl.col("true_range"), pl.col("prev_close"))
    atr_pct = _safe_ratio(pl.col("atr_14"), pl.col("close"))
    rel_volume_20 = _safe_ratio(pl.col("volume"), pl.col("avg_volume_20"))
    rel_volume_5 = _safe_ratio(pl.col("avg_volume_5"), pl.col("avg_volume_20"))

    frame = frame.with_columns(
        cmf_5=cmf_5,
        cmf_20=cmf_20,
        cmf_acceleration=cmf_5 - cmf_20,
        obv_pressure_5=obv_5,
        obv_pressure_20=obv_20,
        obv_acceleration=obv_5 - obv_20,
        up_down_volume_asymmetry=_safe_ratio(
            pl.col("volume_sum_20") - 2.0 * pl.col("down_volume_sum_20"),
            pl.col("volume_sum_20"),
        ),
        down_volume_dryup=(1.0 - _safe_ratio(down_pace_5, down_pace_20)).clip(-2.0, 1.0),
        absorption=(
            rel_volume_20
            * (1.0 - _safe_ratio(range_pct, atr_pct)).clip(-2.0, 1.0)
            * pl.col("close_location").clip(0.0, 1.0)
        ),
        price_impact_efficiency=_safe_ratio(
            pl.col("ret_5"),
            pl.col("turnover").rolling_sum(5, min_samples=5).over("code")
            / pl.col("adv_20"),
        ),
        atr_compression=(
            1.0 - _safe_ratio(pl.col("atr_5"), pl.col("atr_20"))
        ).clip(-2.0, 1.0),
        range_compression=(
            1.0 - _safe_ratio(pl.col("high_20") - pl.col("low_20"), pl.col("close"))
        ),
        rel_volume_5=rel_volume_5,
        rel_volume_20=rel_volume_20,
        volume_trend=_safe_ratio(pl.col("avg_volume_5"), pl.col("avg_volume_20")) - 1.0,
        proximity_high_20=_safe_ratio(pl.col("close"), pl.col("high_20")) - 1.0,
        proximity_high_120=_safe_ratio(pl.col("close"), pl.col("high_120")) - 1.0,
        higher_low=_safe_ratio(pl.col("low_5"), pl.col("low_20")) - 1.0,
        relative_strength_20=pl.col("ret_20") - pl.col("benchmark_ret_20"),
        market_regime=(
            pl.col("benchmark_close")
            > pl.col("benchmark_close")
            .rolling_mean(50, min_samples=40)
            .over("code")
        ).cast(pl.Float64),
    )

    frame = frame.with_columns(
        flow_x_compression=(
            (pl.col("cmf_20") + pl.col("obv_pressure_20")) / 2.0
        )
        * pl.col("atr_compression"),
        absorption_x_proximity=pl.col("absorption")
        * (1.0 + pl.col("proximity_high_20")),
        demand_x_dryup=pl.col("up_down_volume_asymmetry") * pl.col("down_volume_dryup"),
        rs_x_flow_acceleration=pl.col("relative_strength_20")
        * ((pl.col("cmf_acceleration") + pl.col("obv_acceleration")) / 2.0),
    ).with_columns(
        eligible=(
            (pl.col("bars_seen") >= minimum_history)
            & (pl.col("adv_20") >= minimum_adv_bdt)
            & (pl.col("close") > 0)
            & pl.col("clean_feature_history")
        )
    )

    return attach_buckets(frame)


def attach_buckets(frame: pl.DataFrame) -> pl.DataFrame:
    """Point-in-time liquidity deciles and volatility terciles for matched controls."""
    eligible_count = pl.len().over("date")
    return frame.with_columns(
        liq_decile=(
            pl.col("adv_20").rank("ordinal").over("date") * 10 / eligible_count
        )
        .floor()
        .clip(0, 9)
        .cast(pl.Int8),
        vol_tercile=(
            pl.col("vol_60").rank("ordinal").over("date") * 3 / eligible_count
        )
        .floor()
        .clip(0, 2)
        .cast(pl.Int8),
    )


def attach_triple_barrier(
    frame: pl.DataFrame,
    *,
    horizon: int,
    target_return: float,
    stop_return: float,
    suffix: str,
    suspicious_drop: float = -0.10,
) -> pl.DataFrame:
    """Attach next-open triple-barrier outcomes to each row.

    Profit and stop levels are evaluated against each future session's high and low. When both
    are touched in one daily bar, the stop is recorded first. A future raw-close fall deeper than
    the DSE circuit band invalidates the label as a likely corporate-action rebase.
    """
    if horizon < 1:
        raise ValueError("horizon must be positive")
    ordered = frame.sort(["code", "date"]).with_row_index("_demand_row")
    outputs: dict[str, list[Any]] = {
        f"label_{suffix}": [],
        f"state_{suffix}": [],
        f"entry_date_{suffix}": [],
        f"exit_date_{suffix}": [],
        f"entry_price_{suffix}": [],
        f"gross_return_{suffix}": [],
        f"mfe_{suffix}": [],
        f"mae_{suffix}": [],
        f"label_valid_{suffix}": [],
    }

    for group in ordered.partition_by("code", maintain_order=True):
        dates = group["date"].to_list()
        opens = group["open"].to_numpy()
        highs = group["high"].to_numpy()
        lows = group["low"].to_numpy()
        closes = group["close"].to_numpy()
        n = group.height

        group_values = {key: [None] * n for key in outputs}
        for signal_index in range(n):
            final_index = signal_index + horizon
            entry_index = signal_index + 1
            if final_index >= n or entry_index >= n:
                continue
            entry = float(opens[entry_index])
            if not math.isfinite(entry) or entry <= 0:
                continue

            target_price = entry * (1.0 + target_return)
            stop_price = entry * (1.0 - stop_return)
            state = "timeout"
            label = 0
            exit_index = final_index
            exit_return = float(closes[final_index] / entry - 1.0)
            label_valid = True

            future_highs = highs[entry_index : final_index + 1]
            future_lows = lows[entry_index : final_index + 1]
            prior_closes = closes[signal_index:final_index]
            future_closes = closes[entry_index : final_index + 1]
            close_returns = future_closes / prior_closes - 1.0
            if np.any(close_returns <= suspicious_drop):
                label_valid = False

            for offset, (high, low) in enumerate(
                zip(future_highs, future_lows, strict=True)
            ):
                current_index = entry_index + offset
                hit_stop = low <= stop_price
                hit_target = high >= target_price
                if hit_stop:
                    state = "stop"
                    label = 0
                    exit_index = current_index
                    exit_return = -stop_return
                    break
                if hit_target:
                    state = "target"
                    label = 1
                    exit_index = current_index
                    exit_return = target_return
                    break

            group_values[f"label_{suffix}"][signal_index] = label
            group_values[f"state_{suffix}"][signal_index] = state
            group_values[f"entry_date_{suffix}"][signal_index] = dates[entry_index]
            group_values[f"exit_date_{suffix}"][signal_index] = dates[exit_index]
            group_values[f"entry_price_{suffix}"][signal_index] = entry
            group_values[f"gross_return_{suffix}"][signal_index] = exit_return
            group_values[f"mfe_{suffix}"][signal_index] = (
                float(np.max(future_highs) / entry - 1.0)
            )
            group_values[f"mae_{suffix}"][signal_index] = (
                float(np.min(future_lows) / entry - 1.0)
            )
            group_values[f"label_valid_{suffix}"][signal_index] = label_valid

        for key in outputs:
            outputs[key].extend(group_values[key])

    columns = [
        pl.Series(name, values)
        for name, values in outputs.items()
    ]
    return ordered.with_columns(columns).drop("_demand_row")


def purged_window(
    frame: pl.DataFrame,
    *,
    start: dt.date | None,
    end: dt.date,
    label_end_column: str,
) -> pl.DataFrame:
    """Return signals whose complete outcome is known inside the requested window."""
    predicate = (pl.col("date") <= end) & (pl.col(label_end_column) <= end)
    if start is not None:
        predicate &= pl.col("date") >= start
    return frame.filter(predicate)


def _finite_training_frame(
    frame: pl.DataFrame,
    *,
    target_column: str,
    feature_names: tuple[str, ...],
) -> tuple[pl.DataFrame, np.ndarray, np.ndarray]:
    selected = frame.filter(pl.col("eligible") & pl.col(target_column).is_not_null()).drop_nulls(
        [*feature_names, target_column]
    )
    if selected.is_empty():
        raise ValueError("No complete eligible training rows")
    matrix = selected.select(feature_names).to_numpy().astype(float)
    target = selected[target_column].to_numpy().astype(float)
    finite = np.isfinite(matrix).all(axis=1) & np.isfinite(target)
    selected = selected.filter(pl.Series(finite))
    matrix = matrix[finite]
    target = target[finite]
    if len(np.unique(target)) != 2:
        raise ValueError("Training labels must contain both classes")
    return selected, matrix, target


def fit_ridge_logit(
    frame: pl.DataFrame,
    *,
    target_column: str = "label_primary",
    feature_names: tuple[str, ...] = FEATURE_COLUMNS,
    l2_penalty: float = 4.0,
    max_iterations: int = 100,
    tolerance: float = 1e-7,
) -> RidgeLogitModel:
    """Fit a balanced ridge logistic model with deterministic Newton updates."""
    _, matrix, target = _finite_training_frame(
        frame,
        target_column=target_column,
        feature_names=feature_names,
    )
    means = matrix.mean(axis=0)
    scales = matrix.std(axis=0)
    scales = np.where(scales > 1e-12, scales, 1.0)
    x = (matrix - means) / scales
    design = np.column_stack([np.ones(x.shape[0]), x])

    positives = max(1, int(target.sum()))
    negatives = max(1, int(len(target) - target.sum()))
    sample_weights = np.where(
        target == 1.0,
        len(target) / (2.0 * positives),
        len(target) / (2.0 * negatives),
    )
    theta = np.zeros(design.shape[1], dtype=float)
    penalty = np.diag([0.0, *([l2_penalty] * x.shape[1])])
    converged = False
    completed_iterations = 0

    for iteration in range(1, max_iterations + 1):
        logits = np.clip(design @ theta, -35.0, 35.0)
        probability = 1.0 / (1.0 + np.exp(-logits))
        curvature = sample_weights * probability * (1.0 - probability)
        gradient = design.T @ (sample_weights * (probability - target)) + penalty @ theta
        hessian = design.T @ (curvature[:, None] * design) + penalty
        hessian += np.eye(hessian.shape[0]) * 1e-8
        step = np.linalg.solve(hessian, gradient)
        theta -= step
        completed_iterations = iteration
        if float(np.max(np.abs(step))) < tolerance:
            converged = True
            break

    return RidgeLogitModel(
        feature_names=feature_names,
        means=tuple(float(value) for value in means),
        scales=tuple(float(value) for value in scales),
        coefficients=tuple(float(value) for value in theta[1:]),
        intercept=float(theta[0]),
        iterations=completed_iterations,
        converged=converged,
    )


def attach_scores(
    frame: pl.DataFrame,
    model: RidgeLogitModel,
    *,
    score_column: str = "demand_score",
) -> pl.DataFrame:
    """Score complete eligible rows while retaining nulls for ineligible evidence."""
    complete = frame.select(model.feature_names).null_count().row(0)
    del complete  # schema validation happens in the selection below
    matrix = frame.select(model.feature_names).to_numpy().astype(float)
    valid = (
        frame["eligible"].fill_null(False).to_numpy().astype(bool)
        & np.isfinite(matrix).all(axis=1)
    )
    scores = np.full(frame.height, np.nan)
    scores[valid] = model.predict(matrix[valid])
    return frame.with_columns(
        pl.Series(score_column, scores).fill_nan(None)
    )


def discovery_threshold(
    scored_discovery: pl.DataFrame,
    *,
    quantile: float,
    score_column: str = "demand_score",
) -> float:
    values = (
        scored_discovery.filter(pl.col("eligible"))
        .drop_nulls(score_column)[score_column]
        .to_numpy()
    )
    if values.size == 0:
        raise ValueError("No discovery scores available")
    return float(np.quantile(values, quantile))


def select_candidates(
    frame: pl.DataFrame,
    *,
    threshold: float,
    top_n: int,
    score_column: str = "demand_score",
) -> pl.DataFrame:
    """Select at most ``top_n`` frozen-threshold candidates per signal session."""
    if top_n < 1:
        raise ValueError("top_n must be positive")
    return (
        frame.filter(
            pl.col("eligible")
            & pl.col(score_column).is_not_null()
            & (pl.col(score_column) >= threshold)
        )
        .sort(["date", score_column, "code"], descending=[False, True, False])
        .group_by("date", maintain_order=True)
        .head(top_n)
        .with_columns(selection_rank=pl.col("code").cum_count().over("date"))
    )


def _bootstrap_mean(
    values: np.ndarray,
    *,
    block: int,
    draws: int = 2_000,
    seed: int = 20260726,
) -> tuple[float, float]:
    if values.size == 0:
        return float("nan"), float("nan")
    block = max(1, min(block, values.size))
    blocks = math.ceil(values.size / block)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, values.size, size=(draws, blocks))
    offsets = np.arange(block)
    indices = (starts[:, :, None] + offsets).reshape(draws, -1) % values.size
    means = values[indices[:, : values.size]].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(low), float(high)


def evaluate_window(
    frame: pl.DataFrame,
    candidates: pl.DataFrame,
    *,
    window: str,
    horizon: int,
    one_way_cost_bps: float,
    stressed_one_way_cost_bps: float,
    suffix: str = "primary",
) -> WindowResult:
    """Measure top-candidate classification and executable next-open returns."""
    label = f"label_{suffix}"
    gross = f"gross_return_{suffix}"
    mfe = f"mfe_{suffix}"
    mae = f"mae_{suffix}"
    eligible = frame.filter(
        pl.col("eligible")
        & pl.col(label).is_not_null()
        & pl.col(f"label_valid_{suffix}")
    ).drop_nulls(["liq_decile", "vol_tercile", gross])
    selected = candidates.join(
        eligible.select(["code", "date"]),
        on=["code", "date"],
        how="semi",
    )
    if selected.is_empty():
        return WindowResult(
            window=window,
            eligible_rows=eligible.height,
            selected_events=0,
            selected_dates=0,
            base_rate=None,
            precision=None,
            precision_lift_pp=None,
            matched_precision_lift_pp=None,
            mean_gross_return_pct=None,
            mean_net_return_pct=None,
            mean_stressed_return_pct=None,
            matched_excess_net_pct=None,
            hit_rate_pct=None,
            median_mfe_pct=None,
            median_mae_pct=None,
            net_ci_low_pct=None,
            net_ci_high_pct=None,
        )

    group_columns = ["date", "liq_decile", "vol_tercile"]
    control = eligible.with_columns(
        _label_sum=pl.col(label).sum().over(group_columns),
        _label_count=pl.col(label).count().over(group_columns),
        _return_sum=pl.col(gross).sum().over(group_columns),
        _return_count=pl.col(gross).count().over(group_columns),
    ).with_columns(
        matched_label=pl.when(pl.col("_label_count") > 1)
        .then((pl.col("_label_sum") - pl.col(label)) / (pl.col("_label_count") - 1))
        .otherwise(None),
        matched_return=pl.when(pl.col("_return_count") > 1)
        .then((pl.col("_return_sum") - pl.col(gross)) / (pl.col("_return_count") - 1))
        .otherwise(None),
    )
    selected = selected.join(
        control.select(
            [
                "code",
                "date",
                label,
                gross,
                mfe,
                mae,
                "matched_label",
                "matched_return",
            ]
        ),
        on=["code", "date"],
        how="inner",
    )

    normal_cost = one_way_cost_bps / 10_000.0
    stressed_cost = stressed_one_way_cost_bps / 10_000.0
    selected = selected.with_columns(
        net_return=(1.0 + pl.col(gross)) * (1.0 - normal_cost) ** 2 - 1.0,
        stressed_return=(1.0 + pl.col(gross)) * (1.0 - stressed_cost) ** 2 - 1.0,
    ).with_columns(
        matched_excess_net=pl.col("net_return") - pl.col("matched_return")
    )
    per_date = selected.group_by("date").agg(net=pl.col("net_return").mean()).sort("date")
    low, high = _bootstrap_mean(per_date["net"].to_numpy(), block=horizon)
    base_rate = float(eligible[label].mean()) if eligible.height else None
    precision = float(selected[label].mean())
    matched_lift = selected["matched_label"].drop_nulls()
    matched_precision_lift = (
        float(
            (
                selected.filter(pl.col("matched_label").is_not_null())[label]
                - selected.filter(pl.col("matched_label").is_not_null())["matched_label"]
            ).mean()
        )
        if len(matched_lift)
        else None
    )

    return WindowResult(
        window=window,
        eligible_rows=eligible.height,
        selected_events=selected.height,
        selected_dates=selected["date"].n_unique(),
        base_rate=base_rate,
        precision=precision,
        precision_lift_pp=(precision - base_rate) * 100 if base_rate is not None else None,
        matched_precision_lift_pp=(
            matched_precision_lift * 100 if matched_precision_lift is not None else None
        ),
        mean_gross_return_pct=float(selected[gross].mean()) * 100,
        mean_net_return_pct=float(selected["net_return"].mean()) * 100,
        mean_stressed_return_pct=float(selected["stressed_return"].mean()) * 100,
        matched_excess_net_pct=float(selected["matched_excess_net"].drop_nulls().mean()) * 100,
        hit_rate_pct=float((selected["net_return"] > 0).mean()) * 100,
        median_mfe_pct=float(selected[mfe].median()) * 100,
        median_mae_pct=float(selected[mae].median()) * 100,
        net_ci_low_pct=low * 100,
        net_ci_high_pct=high * 100,
    )


def simulate_slot_portfolio(
    candidates: pl.DataFrame,
    benchmark: pl.DataFrame,
    *,
    slots: int,
    one_way_cost_bps: float,
    suffix: str = "primary",
) -> PortfolioResult:
    """Assign ranked candidates to independent capital slots without overlapping a slot."""
    if slots < 1:
        raise ValueError("slots must be positive")
    required = [
        f"entry_date_{suffix}",
        f"exit_date_{suffix}",
        f"gross_return_{suffix}",
        "selection_rank",
        "demand_score",
    ]
    events = (
        candidates.drop_nulls(required)
        .sort(
            [f"entry_date_{suffix}", "selection_rank", "demand_score"],
            descending=[False, False, True],
        )
        .to_dicts()
    )
    slot_available: list[dt.date | None] = [None] * slots
    slot_values = [1.0 / slots] * slots
    timeline: list[tuple[dt.date, int, float]] = []
    accepted: list[dict[str, Any]] = []
    rejected = 0
    cost = one_way_cost_bps / 10_000.0

    for event in events:
        entry_date = event[f"entry_date_{suffix}"]
        available = [
            index
            for index, date in enumerate(slot_available)
            if date is None or date < entry_date
        ]
        if not available:
            rejected += 1
            continue
        slot = min(
            available,
            key=lambda index: slot_available[index] or dt.date.min,
        )
        net_return = (
            (1.0 + float(event[f"gross_return_{suffix}"])) * (1.0 - cost) ** 2 - 1.0
        )
        new_value = slot_values[slot] * (1.0 + net_return)
        slot_values[slot] = new_value
        slot_available[slot] = event[f"exit_date_{suffix}"]
        timeline.append((event[f"exit_date_{suffix}"], slot, new_value))
        accepted.append(event)

    if not accepted:
        return PortfolioResult(
            trades=0,
            rejected_for_slots=rejected,
            total_return_pct=0.0,
            benchmark_return_pct=None,
            excess_return_pct=None,
            maximum_drawdown_pct=0.0,
            win_rate_pct=None,
        )

    replay_values = [1.0 / slots] * slots
    nav_path = [1.0]
    for _, slot, value in sorted(timeline):
        replay_values[slot] = value
        nav_path.append(sum(replay_values))
    nav = np.asarray(nav_path)
    peaks = np.maximum.accumulate(nav)
    max_drawdown = float(np.min(nav / peaks - 1.0) * 100)
    total_return = (sum(slot_values) - 1.0) * 100

    benchmark_map = {
        row["date"]: row["benchmark_close"]
        for row in benchmark.drop_nulls("benchmark_close").sort("date").to_dicts()
    }
    first_entry = min(event[f"entry_date_{suffix}"] for event in accepted)
    last_exit = max(event[f"exit_date_{suffix}"] for event in accepted)
    benchmark_return = None
    if first_entry in benchmark_map and last_exit in benchmark_map:
        benchmark_return = (
            float(benchmark_map[last_exit] / benchmark_map[first_entry] - 1.0) * 100
        )
    wins = sum(
        1
        for event in accepted
        if (
            (1.0 + float(event[f"gross_return_{suffix}"])) * (1.0 - cost) ** 2 - 1.0
        )
        > 0
    )
    return PortfolioResult(
        trades=len(accepted),
        rejected_for_slots=rejected,
        total_return_pct=total_return,
        benchmark_return_pct=benchmark_return,
        excess_return_pct=(
            total_return - benchmark_return if benchmark_return is not None else None
        ),
        maximum_drawdown_pct=abs(max_drawdown),
        win_rate_pct=wins / len(accepted) * 100,
    )
