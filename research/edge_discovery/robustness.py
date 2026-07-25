"""Robustness gates: parameter sensitivity, walk-forward folds, multiple-testing correction.

A single favourable window is not evidence. These three tests are what separate an edge from a
lucky parameterisation, and each one is capable of killing a candidate on its own:

* **Sensitivity** — perturb every threshold by ±25%. A real effect degrades smoothly; an
  artefact flips sign. A candidate whose sign flips inside the band is rejected.
* **Walk-forward** — rolling train/test folds. We report the *dispersion* across folds, not the
  best fold, because the best fold is what overfitting looks like.
* **Deflated Sharpe** — the Sharpe of the best of N trials is upward-biased even when every
  trial is worthless. Deflation is computed over the trial count actually run, which is why the
  ledger records failures: undercounting trials inflates the statistic.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages/analytics/src"))

from edge_discovery import harness, signals

from bulls.analytics.deflated_sharpe import (
    deflated_sharpe_ratio,
    sharpe_moments,
)

SENSITIVITY_BAND = 0.25


def _perturbations(thresholds: dict[str, float]) -> list[tuple[str, dict[str, float]]]:
    """Each threshold moved to -25% and +25% of its registered value, one at a time."""
    out: list[tuple[str, dict[str, float]]] = []
    for name, value in thresholds.items():
        for direction, factor in (
            ("minus25", 1 - SENSITIVITY_BAND),
            ("plus25", 1 + SENSITIVITY_BAND),
        ):
            perturbed = dict(thresholds)
            perturbed[name] = value * factor
            out.append((f"{name}:{direction}", perturbed))
    return out


def _signal_for(key: str, thresholds: dict[str, float]) -> pl.Expr | None:
    """Rebuild a signal expression from perturbed thresholds."""
    t = thresholds
    if key.startswith("us_trend_pullback") or key == "dse_trend_pullback_20d":
        return signals.trend_pullback(
            t.get("pullback_atr", 1.5), t.get("near_sma20_pct", 0.02), t.get("mom_pctile", 0.60)
        )
    if key in ("us_compression_breakout", "dse_compression_breakout"):
        return signals.compression_breakout(
            t.get("atr_contraction", 0.8), t.get("vol_multiple", 1.5), t.get("from_high_pct", -0.15)
        )
    if key in ("us_failed_breakdown", "dse_failed_breakdown"):
        return signals.failed_breakdown(t.get("reclaim_pct", 1.02), t.get("relvol", 1.2))
    if key in ("us_reversal_5d", "dse_reversal_5d"):
        return signals.reversal("ret_5", t.get("decile", 0.10))
    if key in ("us_momentum_12_1", "dse_momentum_12_1"):
        return signals.momentum_top(t.get("decile", 0.10))
    if key == "us_momentum_with_pullback":
        return signals.momentum_with_pullback(t.get("mom_decile", 0.10), t.get("st_pctile", 0.30))
    if key == "us_capitulation_volume":
        return signals.capitulation(t.get("decline", -0.12), t.get("vol_multiple", 2.5))
    return None


def sensitivity(panel: pl.DataFrame, registered, windows: harness.Windows) -> list[dict]:
    """Re-score a hypothesis at every ±25% perturbation of its registered thresholds."""
    spec = registered.spec
    if not spec.thresholds:
        return []

    min_liq = 5 if any(k in spec.key for k in ("reversal", "pullback", "capitulation")) else 4
    gate = (
        signals.eligible(min_liq_decile=min_liq, min_price=0.0, min_bars=120)
        if spec.market == "DSE"
        else signals.eligible(min_liq_decile=min_liq)
    )
    universe = harness.attach_control(panel.filter(gate), spec.horizon)

    rows = []
    for label, thresholds in [
        ("registered", dict(spec.thresholds)),
        *_perturbations(spec.thresholds),
    ]:
        expr = _signal_for(spec.key, thresholds)
        if expr is None:
            continue
        events = universe.filter(expr)
        if events.is_empty():
            rows.append({"spec_key": spec.key, "perturbation": label, "outcome": "no_events"})
            continue
        # Sensitivity is judged out-of-sample: discovery is where thresholds were chosen.
        split = harness.split_events(events, windows)
        oos = (
            pl.concat([split["validation"], split["holdout"]])
            if not split["validation"].is_empty()
            else split["holdout"]
        )
        if oos.is_empty():
            continue
        result = harness.evaluate(oos, replace(spec, key=f"{spec.key}[{label}]"), "oos")
        if result:
            rows.append(
                {
                    "spec_key": spec.key,
                    "perturbation": label,
                    "events": result.events,
                    "excess_bps": round(result.mean_excess_bps, 1),
                    "t_stat": round(result.t_stat, 2),
                    "cost_3x_bps": round(result.cost_3x_bps, 1),
                }
            )
    return rows


def walk_forward(panel: pl.DataFrame, registered, fold_years: int = 2) -> list[dict]:
    """Score the hypothesis on consecutive non-overlapping calendar folds."""
    spec = registered.spec
    signal_fn = signals.SIGNALS.get(spec.key)
    if signal_fn is None:
        return []

    min_liq = 5 if any(k in spec.key for k in ("reversal", "pullback", "capitulation")) else 4
    gate = (
        signals.eligible(min_liq_decile=min_liq, min_price=0.0, min_bars=120)
        if spec.market == "DSE"
        else signals.eligible(min_liq_decile=min_liq)
    )
    universe = harness.attach_control(panel.filter(gate), spec.horizon)
    events = universe.filter(signal_fn())
    if events.is_empty():
        return []

    events = events.with_columns(year=pl.col("date").dt.year())
    years = sorted(events["year"].unique().to_list())
    rows = []
    for start in range(years[0], years[-1] + 1, fold_years):
        fold = events.filter(pl.col("year").is_between(start, start + fold_years - 1))
        if fold.is_empty():
            continue
        result = harness.evaluate(fold, spec, f"{start}-{start + fold_years - 1}")
        if result:
            rows.append(
                {
                    "spec_key": spec.key,
                    "fold": f"{start}-{start + fold_years - 1}",
                    "events": result.events,
                    "excess_bps": round(result.mean_excess_bps, 1),
                    "t_stat": round(result.t_stat, 2),
                    "sharpe": round(result.sharpe, 2),
                }
            )
    return rows


def deflate(
    sharpes: list[float], candidate_sharpe: float, observations: int, series: np.ndarray
) -> dict:
    """Deflated Sharpe for a candidate given the full set of trials actually run."""
    moments = sharpe_moments(series.tolist())
    if moments is None or len(sharpes) < 2:
        return {"deflated_sharpe": None, "trials": len(sharpes)}
    trials_std = float(np.std(sharpes, ddof=1))
    result = deflated_sharpe_ratio(moments, num_trials=len(sharpes), trials_sharpe_std=trials_std)
    return {
        "deflated_sharpe": round(result.deflated_sharpe_ratio, 4),
        "probabilistic_sharpe": round(result.probabilistic_sharpe_ratio, 4),
        "expected_max_sharpe_by_chance": round(result.expected_maximum_sharpe, 4),
        "observed_sharpe": round(candidate_sharpe, 4),
        "trials": len(sharpes),
        "observations": observations,
    }
