"""Scheme-3 — sweep the 'how far below the 1-year high' threshold.

Scheme-3 currently requires a name to be >40% below its 1-year high (deeply washed out). This varies
that depth from shallow (only -20% off the high) to deep (-50%), holding everything else fixed, to see
whether requiring a smaller drop helps (catch them earlier) or hurts (shallow dips don't bounce as far).

    uv run python scripts/deep_study.py
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

from portfolio_backtest import MIN_AVG_VOL, WARMUP, _load, dsex_return, simulate
from scheme2_value import _fundamentals_at, _load_fundamentals
from schemes import _prep

EXITS = dict(stop=-0.10, target=0.25, hold=63, max_pos=10)
DEPTHS = [-20, -25, -30, -35, -40, -50]  # % below the 1-year high


def _signals(by_code, fin, div, deep):
    sigs = defaultdict(set)
    for code, bars in by_code.items():
        if sum(x.volume for x in bars[-20:]) / 20 < MIN_AVG_VOL:
            continue
        c, h, _r, _s20, _s200, _v20, hi, lo = _prep(bars)
        for i in range(WARMUP, len(bars)):
            if not c[i] or not hi[i] or hi[i] <= lo[i]:
                continue
            below = (c[i] / hi[i] - 1) * 100
            pos = (c[i] - lo[i]) / (hi[i] - lo[i]) * 100
            if below < deep and pos < 15 and c[i] > max(h[i - 5 : i]):
                fa = _fundamentals_at(code, c[i], bars[i].date.year, fin, div)
                if fa and fa[0] <= 25:  # profitable + cheap
                    sigs[code].add(bars[i].date)
    return sigs


async def _run():
    by_code, dsex = await _load()
    index_return = dsex_return(dsex)
    fin, div = await _load_fundamentals("DSE")
    print("Scheme-3 — required drop below the 1-year high (everything else fixed)")
    print(f"Reference — full-window DSEX price return: {index_return:+.1f}%\n")
    print(f"{'drop below high':>16}{'total%':>9}{'CAGR%':>8}{'maxDD%':>9}{'win%':>7}{'trades':>8}")
    print("-" * 58)
    for deep in DEPTHS:
        sigs = _signals(by_code, fin, div, deep)
        m = simulate(by_code, dsex, signal_fn=lambda b, s=sigs: s.get(b[0].code, set()), **EXITS)
        tag = "  <- current" if deep == -40 else ""
        print(
            f"{f'>{abs(deep)}% off high':>16}{m['total']:>+9.1f}{m['cagr']:>+8.1f}"
            f"{m['maxdd']:>9.1f}{m['winrate']:>6.0f}%{m['n_trades']:>8}{tag}"
        )


if __name__ == "__main__":
    asyncio.run(_run())
