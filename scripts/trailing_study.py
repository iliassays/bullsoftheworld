"""Let winners run — does a trailing stop compound faster than the fixed +25% target?

Same Scheme-3 entries, same -10% initial stop, same 10 positions. The only change: instead of selling
every winner at +25%, ride it with a trailing stop (exit when it falls X% from its peak) and a longer
time cap. If winners grow bigger, the average win and the compound rate should rise — at the cost of
giving a little back from the peak on each exit.

    uv run python scripts/trailing_study.py
"""

from __future__ import annotations

import asyncio

from portfolio_backtest import _load, dsex_return, simulate
from scheme2_value import _load_fundamentals
from scheme_lab import quality_reversal


async def _run():
    by_code, dsex = await _load()
    index_return = dsex_return(dsex)
    fin, div = await _load_fundamentals("DSE")
    sigs = quality_reversal(by_code, fin, div)

    def fn(b):
        return sigs.get(b[0].code, set())

    configs = [
        ("fixed +25% target (current)", dict(target=0.25, hold=63)),
        ("trail 10% / hold 180d", dict(trail=0.10, hold=180)),
        ("trail 15% / hold 180d", dict(trail=0.15, hold=180)),
        ("trail 20% / hold 252d", dict(trail=0.20, hold=252)),
        ("trail 15% / hold 252d", dict(trail=0.15, hold=252)),
    ]
    print("Scheme-3 — fixed target vs 'let winners run' (trailing stop) · stop -10% / 10 positions")
    print(f"Reference — full-window DSEX price return: {index_return:+.1f}%\n")
    print(
        f"{'EXIT RULE':<30}{'total%':>9}{'CAGR%':>8}{'maxDD%':>9}{'win%':>7}{'avg win':>9}{'trades':>8}"
    )
    print("-" * 80)
    for name, kw in configs:
        m = simulate(by_code, dsex, signal_fn=fn, stop=-0.10, max_pos=10, **kw)
        print(
            f"{name:<30}{m['total']:>+9.1f}{m['cagr']:>+8.1f}{m['maxdd']:>9.1f}"
            f"{m['winrate']:>6.0f}%{m['avg_win']:>+8.0f}%{m['n_trades']:>8}"
        )


if __name__ == "__main__":
    asyncio.run(_run())
