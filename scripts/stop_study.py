"""Stop-loss study for Scheme-3 (the flagship) — what does the data say the SL should be?

The live stop is -10%. This sweeps the stop from tight (-6%) to loose (-20%) on Scheme-3, holding
target/hold/positions at base, so we can see the real trade-off: a tighter stop cuts losers fast but
gets whipsawed out of eventual winners; a looser stop rides through noise but bleeds more when wrong.

    uv run python scripts/stop_study.py
"""

from __future__ import annotations

import asyncio

from portfolio_backtest import _load, simulate
from scheme2_value import _load_fundamentals
from scheme_lab import quality_reversal

STOPS = [-0.06, -0.08, -0.10, -0.12, -0.15, -0.20]
BASE = dict(target=0.25, hold=63, max_pos=10)
INDEX = 7.8


async def _run():
    by_code, dsex = await _load()
    fin, div = await _load_fundamentals("DSE")
    sigs = quality_reversal(by_code, fin, div)

    def fn(b):
        return sigs.get(b[0].code, set())

    print("Scheme-3 (Quality Reversal) — stop-loss sweep · target +25% / hold 63d / 10 positions")
    print(f"Reference — buy & hold DSEX: +{INDEX}%\n")
    print(
        f"{'STOP':>6}{'total%':>9}{'CAGR%':>8}{'maxDD%':>9}{'trades':>8}{'win%':>7}{'avg loss':>10}{'vs idx':>8}"
    )
    print("-" * 66)
    for stop in STOPS:
        m = simulate(by_code, dsex, signal_fn=fn, stop=stop, **BASE)
        flag = "  <- current" if stop == -0.10 else ""
        print(
            f"{stop * 100:>5.0f}%{m['total']:>+9.1f}{m['cagr']:>+8.1f}{m['maxdd']:>9.1f}"
            f"{m['n_trades']:>8}{m['winrate']:>6.0f}%{m['avg_loss']:>9.1f}%{m['total'] - INDEX:>+8.1f}{flag}"
        )


if __name__ == "__main__":
    asyncio.run(_run())
