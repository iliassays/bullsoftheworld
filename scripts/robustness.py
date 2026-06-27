"""Robustness sweep — is the edge real, or curve-fit to one lucky setting?

Re-runs the Deep-Value Reversal portfolio backtest while varying ONE knob at a time around the base
config. If total return stays positive and beats the index (+7.8%) across a whole range of each knob,
the edge is structural. If it only works at one exact value (and craters next to it), it's overfit
and not safe to sell. This is the test a skeptical payer should demand.

    uv run python scripts/robustness.py
"""

from __future__ import annotations

import asyncio

from portfolio_backtest import _load, simulate

INDEX_RET = 7.8  # buy & hold DSEX over the window, for reference

BASE = dict(stop=-0.10, target=0.25, hold=63, deep=-40.0, near_low=15.0, max_pos=10)
SWEEPS = {
    "stop": [-0.06, -0.08, -0.10, -0.12, -0.15],
    "target": [0.15, 0.20, 0.25, 0.30, 0.40],
    "hold": [40, 63, 90, 120],
    "deep": [-30.0, -35.0, -40.0, -45.0, -50.0],
    "near_low": [10.0, 15.0, 20.0, 25.0],
    "max_pos": [5, 8, 10, 15, 20],
}


async def _run():
    by_code, dsex = await _load()
    print(f"Base config: {BASE}")
    print(f"Reference — buy & hold DSEX: {INDEX_RET:+.1f}%\n")
    print(
        f"{'KNOB = value':<20}{'total%':>9}{'CAGR%':>8}{'maxDD%':>9}{'trades':>8}{'win%':>7}{'vs index':>10}"
    )
    print("-" * 72)
    for knob, values in SWEEPS.items():
        for v in values:
            params = {**BASE, knob: v}
            m = simulate(by_code, dsex, **params)
            star = " *base" if v == BASE[knob] else ""
            print(
                f"{knob + ' = ' + str(v):<20}{m['total']:>+9.1f}{m['cagr']:>+8.1f}{m['maxdd']:>9.1f}"
                f"{m['n_trades']:>8}{m['winrate']:>6.0f}%{m['total'] - INDEX_RET:>+10.1f}{star}"
            )
        print()


if __name__ == "__main__":
    asyncio.run(_run())
