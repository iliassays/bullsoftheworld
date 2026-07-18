"""Robustness sweep — is the edge real, or curve-fit to one lucky setting?

Re-runs the Deep-Value Reversal portfolio backtest while varying ONE knob at a time around the base
config. Stability across parameters is useful diagnostic evidence, but this legacy same-close engine
cannot establish an institutional edge or support a product performance claim.

    uv run python scripts/robustness.py
"""

from __future__ import annotations

import asyncio

from portfolio_backtest import _load, dsex_return, simulate

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
    index_return = dsex_return(dsex)
    print(f"Base config: {BASE}")
    print(f"Reference — full-window DSEX price return: {index_return:+.1f}%\n")
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
                f"{m['n_trades']:>8}{m['winrate']:>6.0f}%{m['total'] - index_return:>+10.1f}{star}"
            )
        print()


if __name__ == "__main__":
    asyncio.run(_run())
