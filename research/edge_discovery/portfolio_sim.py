"""Portfolio simulation — the test that separates factor efficacy from investability.

    .venv/bin/python research/edge_discovery/portfolio_sim.py

The battery measures excess return over a **matched control**: other securities on the same
session, in the same liquidity decile and volatility tercile. That answers "does this signal beat
comparable stocks?" It does not answer "would holding this have been better than doing nothing?",
and for `us_momentum_12_1` those questions have opposite answers — it beats its peer group by
~49bps per holding and still loses to SPY, because the peer group itself underperformed the
cap-weighted index over the sample.

This module therefore exists to stop a control-relative number from being read as an edge. Any
strategy Atlas describes as having an edge must clear this simulation against an independent
passive benchmark, as an actual capital-constrained portfolio.

Construction: overlapping cohorts, the standard approach for a signal with a fixed holding
period. On each session the portfolio holds every name signalled in the previous ``horizon``
sessions, equal weighted. Round-trip costs are charged half on the entry session and half on the
exit session, by liquidity decile. Entry is never same-bar — a signal at ``t`` first contributes
a return on ``t+1``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from edge_discovery import dataset, harness, signals
from edge_discovery.run_battery import build_panel

HORIZON = 21


def simulate(panel: pl.DataFrame, signal: pl.Expr, horizon: int = HORIZON) -> dict:
    """Equal-weight overlapping-cohort portfolio; returns NAV path and risk metrics."""
    universe = panel.filter(signals.eligible(min_liq_decile=4))
    picks = universe.filter(signal).select(["code", "date", "liq_decile"])

    sessions = panel.select("date").unique().sort("date")["date"].to_list()
    index = {day: i for i, day in enumerate(sessions)}

    # Expand each signal into the `horizon` sessions it is held. Offset starts at 1: a signal
    # observed at the close of `t` cannot contribute a return until `t+1`.
    offsets = pl.DataFrame({"k": list(range(1, horizon + 1))}, schema={"k": pl.Int32})
    held = (
        picks.with_columns(i=pl.col("date").replace_strict(index, return_dtype=pl.Int32))
        .select(["code", "i", "liq_decile"])
        .join(offsets, how="cross")
        .with_columns(hold_i=pl.col("i") + pl.col("k"))
    )

    returns = panel.select(["code", "date", "ret"]).with_columns(
        hold_i=pl.col("date").replace_strict(index, return_dtype=pl.Int32)
    )
    joined = held.join(returns, on=["code", "hold_i"], how="inner").drop_nulls("ret")

    cost = pl.col("liq_decile").replace_strict(harness.COST_BPS_NORMAL, default=150.0) / 10_000
    joined = joined.with_columns(
        net_ret=pl.col("ret")
        - pl.when(pl.col("k").is_in([1, horizon])).then(cost / 2).otherwise(0.0)
    )

    daily = joined.group_by("date").agg(r=pl.col("net_ret").mean(), n=pl.len()).sort("date")
    r = daily["r"].to_numpy()
    equity = np.cumprod(1 + r)
    peak = np.maximum.accumulate(equity)
    years = (daily["date"].max() - daily["date"].min()).days / 365.25

    return {
        "start": daily["date"].min(),
        "end": daily["date"].max(),
        "years": years,
        "avg_positions": float(daily["n"].mean()),
        "nav_per_100": float(100 * equity[-1]),
        "total_return_pct": float((equity[-1] - 1) * 100),
        "cagr_pct": float((equity[-1] ** (1 / years) - 1) * 100),
        "max_drawdown_pct": float((equity / peak - 1).min() * 100),
        "annual_vol_pct": float(r.std() * np.sqrt(252) * 100),
    }


def benchmark(code: str, start, end) -> dict:
    """Passive buy-and-hold over the identical window."""
    bars = (
        dataset.benchmarks()
        .filter((pl.col("code") == code) & pl.col("date").is_between(start, end))
        .sort("date")
    )
    prices = bars["adjusted_close"].to_numpy()
    growth = prices[-1] / prices[0]
    years = (bars["date"].max() - bars["date"].min()).days / 365.25
    daily = np.diff(prices) / prices[:-1]
    equity = np.cumprod(1 + daily)
    peak = np.maximum.accumulate(equity)
    return {
        "nav_per_100": float(100 * growth),
        "total_return_pct": float((growth - 1) * 100),
        "cagr_pct": float((growth ** (1 / years) - 1) * 100),
        "max_drawdown_pct": float((equity / peak - 1).min() * 100),
        "annual_vol_pct": float(daily.std() * np.sqrt(252) * 100),
    }


def main() -> None:
    panel = build_panel("US")
    strategy = simulate(panel, signals.momentum_top(0.10))
    passive = benchmark("SPY", strategy["start"], strategy["end"])

    print(f"us_momentum_12_1 portfolio simulation, {HORIZON}-session overlapping cohorts")
    print(
        f"  window            : {strategy['start']} -> {strategy['end']} "
        f"({strategy['years']:.1f} years)"
    )
    print(f"  avg positions held: {strategy['avg_positions']:.0f}\n")

    header = f"  {'metric':<22}{'momentum':>14}{'SPY':>14}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for label, key, fmt in (
        ("$100 becomes", "nav_per_100", "${:,.2f}"),
        ("total return", "total_return_pct", "{:,.1f}%"),
        ("CAGR", "cagr_pct", "{:.2f}%"),
        ("max drawdown", "max_drawdown_pct", "{:.1f}%"),
        ("annual volatility", "annual_vol_pct", "{:.1f}%"),
    ):
        print(f"  {label:<22}{fmt.format(strategy[key]):>14}{fmt.format(passive[key]):>14}")

    gap = strategy["cagr_pct"] - passive["cagr_pct"]
    print(f"\n  CAGR gap vs passive: {gap:+.2f} pct points")
    if gap < 0:
        print("  VERDICT: does not beat a passive index. A positive matched-control excess is")
        print("           factor efficacy, not investability. Not paper_eligible.")


if __name__ == "__main__":
    main()
