"""How real is the 'starve for cash / miss better stocks' worry? — measure it.

Reconstructs, day by day, how many of the 10 slots were actually occupied across the backtest, how
often the book was FULL (so a new signal would have to wait), how fast slots free up, and how much
of the +74% was just the market rising vs the strategy's own edge. Honest diagnostics, not a pitch.

    uv run python scripts/occupancy_study.py
"""

from __future__ import annotations

import asyncio
import statistics as st

from portfolio_backtest import _load, simulate
from scheme2_value import _load_fundamentals
from scheme_lab import quality_reversal


async def _run():
    by_code, dsex = await _load()
    fin, div = await _load_fundamentals("DSE")
    sigs = quality_reversal(by_code, fin, div)
    m = simulate(
        by_code,
        dsex,
        signal_fn=lambda b: sigs.get(b[0].code, set()),
        stop=-0.10,
        target=0.25,
        hold=63,
        max_pos=10,
    )
    tl = m["trade_log"]
    axis = sorted({b.date for bars in by_code.values() for b in bars})

    # daily occupancy: how many positions were open on each trading day
    occ = []
    for d in axis:
        n = sum(1 for t in tl if t["in_date"] <= d < t["out_date"])
        occ.append(n)
    days = len(occ)
    full = sum(1 for n in occ if n >= 10)
    near = sum(1 for n in occ if n >= 8)
    holds = [t["held"] for t in tl]

    # new buys per month (the real pace you'd act at)
    by_month: dict[tuple[int, int], int] = {}
    for t in tl:
        k = (t["in_date"].year, t["in_date"].month)
        by_month[k] = by_month.get(k, 0) + 1
    pace = list(by_month.values())

    idx = sorted(dsex.items())
    mkt = (idx[-1][1] / idx[0][1] - 1) * 100

    print("=== Would you actually starve for cash? ===")
    print(f"  Trading days in test: {days}")
    print(f"  Average slots filled: {st.mean(occ):.1f} of 10")
    print(f"  Book FULL (10/10), i.e. a new signal must wait: {full / days * 100:.0f}% of days")
    print(f"  Book near-full (>=8/10): {near / days * 100:.0f}% of days")
    print(f"  New buys per active month: median {st.median(pace):.0f}, max {max(pace)}")
    print(
        f"  Holding period before a slot frees: median {st.median(holds)} days, avg {st.mean(holds):.0f}"
    )

    print("\n=== How much of +74% was skill vs the market just rising? ===")
    print(f"  Market (buy & hold DSEX) over the same window: {mkt:+.1f}%")
    print(
        f"  Strategy: {m['total']:+.1f}%  ->  ~{m['total'] - mkt:+.0f}% above the market (the 'edge' part)"
    )
    print(
        f"  Trades: {m['n_trades']} · win {m['winrate']:.0f}% · this is ONE ~2-year regime, EOD-close fills."
    )


if __name__ == "__main__":
    asyncio.run(_run())
