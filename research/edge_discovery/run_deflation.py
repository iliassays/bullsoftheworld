"""Deflated Sharpe for the surviving candidates, corrected over the true trial count.

The trial count is taken from the ledger and the sensitivity sweep together — every
specification actually evaluated, including the ones that failed. Counting only the winners is
the classic way to make an artefact look significant.

    .venv/bin/python research/edge_discovery/run_deflation.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages/analytics/src"))

from edge_discovery import harness, signals
from edge_discovery.hypotheses import PRICE_BASED
from edge_discovery.run_battery import OUT_DIR, build_panel

from bulls.analytics.deflated_sharpe import deflated_sharpe_ratio, sharpe_moments

CANDIDATES = ["us_momentum_12_1", "us_momentum_with_pullback", "us_trend_pullback_h21"]


def per_date_series(panel: pl.DataFrame, registered) -> np.ndarray | None:
    """The out-of-sample per-date net excess series the Sharpe is computed on."""
    spec = registered.spec
    signal_fn = signals.SIGNALS.get(spec.key)
    if signal_fn is None:
        return None
    min_liq = 5 if any(k in spec.key for k in ("reversal", "pullback", "capitulation")) else 4
    universe = harness.attach_control(
        panel.filter(signals.eligible(min_liq_decile=min_liq)), spec.horizon
    )
    events = universe.filter(signal_fn())
    split = harness.split_events(events, harness.US_WINDOWS)
    oos = pl.concat([split["validation"], split["holdout"]])
    fwd = f"fwd_{spec.horizon}"
    oos = oos.drop_nulls([fwd, "control", "liq_decile"])
    if oos.is_empty():
        return None
    cost = pl.col("liq_decile").replace_strict(harness.COST_BPS_NORMAL, default=150.0) / 10_000.0
    scored = oos.with_columns(net=(pl.col(fwd) - pl.col("control")) - cost)
    return scored.group_by("date").agg(m=pl.col("net").mean()).sort("date")["m"].to_numpy()


def main() -> None:
    ledger = json.loads((OUT_DIR / "ledger.json").read_text())
    sensitivity = json.loads((OUT_DIR / "sensitivity.json").read_text())

    # Every distinct specification evaluated anywhere in this program.
    trial_keys = {row["spec_key"] for row in ledger if "events" in row}
    trial_keys |= {
        f"{r['spec_key']}[{r['perturbation']}]" for r in sensitivity if "excess_bps" in r
    }
    num_trials = len(trial_keys)

    # The dispersion of Sharpes across trials, needed for the expected-maximum correction.
    # `deflated_sharpe_ratio` compares against `moments.sharpe`, which is PER PERIOD, so the
    # dispersion must be per period too. The ledger stores annualised Sharpes, so each is
    # divided back by sqrt(252 / horizon). Mixing the two units would inflate the chance
    # benchmark by ~3.5x and manufacture a rejection.
    horizons = {r.spec.key: r.spec.horizon for r in PRICE_BASED}
    sharpes = [
        row["sharpe"] / np.sqrt(252.0 / horizons[row["spec_key"]])
        for row in ledger
        if row.get("sharpe") is not None
        and row["sharpe"] == row["sharpe"]
        and row["spec_key"] in horizons
    ]
    trials_std = float(np.std(sharpes, ddof=1))

    print(f"Trial count for deflation: {num_trials} distinct specifications")
    print(f"Sharpe dispersion across trials: {trials_std:.3f}\n")

    panel = build_panel("US")
    out = []
    for registered in PRICE_BASED:
        if registered.spec.key not in CANDIDATES:
            continue
        series = per_date_series(panel, registered)
        if series is None or len(series) < 30:
            continue
        moments = sharpe_moments(series.tolist())
        if moments is None:
            continue
        result = deflated_sharpe_ratio(
            series.tolist(), num_trials=num_trials, trials_sharpe_std=trials_std
        )
        if result is None:
            continue
        periods_per_year = 252.0 / registered.spec.horizon
        row = {
            "spec_key": registered.spec.key,
            "observations": len(series),
            "sharpe_per_period": round(moments.sharpe, 4),
            "sharpe_annualised": round(moments.sharpe * np.sqrt(periods_per_year), 3),
            "expected_max_by_chance": round(result.benchmark_sharpe, 4),
            "probabilistic_sharpe": round(result.probabilistic_sharpe, 4),
            "deflated_sharpe": round(result.deflated_sharpe, 4),
            "passes_95": result.deflated_sharpe >= 0.95,
        }
        out.append(row)
        print(row)

    (OUT_DIR / "deflated_sharpe.json").write_text(
        json.dumps(
            {"num_trials": num_trials, "trials_sharpe_std": trials_std, "results": out}, indent=2
        )
    )


if __name__ == "__main__":
    main()
