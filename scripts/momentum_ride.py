"""12-month momentum, ride it — test the 'strongest trend' idea properly.

The screenshot's factor: 12-1 momentum (return from ~12 months ago to ~1 month ago, skipping the last
month), optionally risk-adjusted ("steady climbs over wild ones" = momentum / volatility). We buy the
top trenders each month and RIDE them (trailing stop, long hold). Globally momentum works; our earlier
DSE tests said it loses. This is the definitive version. Compared to Scheme-3, with an out-of-sample
split.

Caveat: 12-month momentum needs ~12 months of history, leaving only ~10 months of our 2-year window to
test on — so few rebalances, statistically THIN. Read directionally.

    uv run python scripts/momentum_ride.py
"""

from __future__ import annotations

import asyncio
import datetime as dt
import statistics as st
from collections import defaultdict

from portfolio_backtest import MIN_AVG_VOL, _load, simulate

INDEX = 7.8
TOP_N = 12
SPLIT = dt.date(2025, 9, 1)


def _liquid(by_code):
    return {c: b for c, b in by_code.items() if sum(x.volume for x in b[-20:]) / 20 >= MIN_AVG_VOL}


def _signals(by_code, steady: bool):
    """Monthly: rank by 12-1 momentum (or momentum/vol if steady), take the top-N trenders."""
    liquid = _liquid(by_code)
    prepped = {
        c: ([b.close for b in b_], {b.date: i for i, b in enumerate(b_)})
        for c, b_ in liquid.items()
    }
    axis = sorted({b.date for b_ in liquid.values() for b in b_})
    sigs = defaultdict(set)
    for k in range(273, len(axis), 21):  # need 252 + 21 bars of history first
        d = axis[k]
        scores = {}
        for c, (closes, didx) in prepped.items():
            i = didx.get(d)
            if i is None or i < 252 or not closes[i - 252]:
                continue
            mom = closes[i - 21] / closes[i - 252] - 1  # 12-to-1-month return (skip last month)
            if steady:
                rets = [closes[j] / closes[j - 1] - 1 for j in range(i - 252, i) if closes[j - 1]]
                vol = st.pstdev(rets) if len(rets) > 2 else None
                if not vol:
                    continue
                scores[c] = mom / vol  # risk-adjusted momentum (steady climbs rank higher)
            else:
                scores[c] = mom
        for c in sorted(scores, key=lambda c: scores[c], reverse=True)[:TOP_N]:
            sigs[c].add(d)
    return sigs


async def _run():
    by_code, dsex = await _load()

    def idx(lo, hi):
        v = [x for dd, x in sorted(dsex.items()) if lo <= dd < hi]
        return (v[-1] / v[0] - 1) * 100 if len(v) > 1 else 0

    configs = [
        (
            "12-1 momentum, ride (trail15/252d)",
            _signals(by_code, False),
            dict(stop=-0.12, trail=0.15, hold=252),
        ),
        (
            "12-1 momentum, fixed (+25/-10/126d)",
            _signals(by_code, False),
            dict(stop=-0.10, target=0.25, hold=126),
        ),
        (
            "steady mom (÷vol), ride",
            _signals(by_code, True),
            dict(stop=-0.12, trail=0.15, hold=252),
        ),
    ]
    print("Momentum 'strongest trend' on DSE — buy the top-12 trenders, ride them.")
    print(f"Reference — Scheme-3 (our flagship): +73.6%  |  buy & hold DSEX: +{INDEX}%\n")
    print(f"{'MOMENTUM SCHEME':<38}{'total%':>9}{'maxDD%':>9}{'win%':>7}{'trades':>8}{'vs idx':>8}")
    print("-" * 80)
    best = None
    for name, sigs, ex in configs:
        m = simulate(
            by_code, dsex, signal_fn=lambda b, s=sigs: s.get(b[0].code, set()), max_pos=10, **ex
        )
        print(
            f"{name:<38}{m['total']:>+9.1f}{m['maxdd']:>9.1f}{m['winrate']:>6.0f}%{m['n_trades']:>8}{m['total'] - INDEX:>+8.1f}"
        )
        if best is None or m["total"] > best[1]["total"]:
            best = (name, m, sigs, ex)

    name, _m, sigs, ex = best
    print(f"\nOut-of-sample check on the best ({name}), split {SPLIT}:")
    for label, lo, hi in (
        ("TRAIN", dt.date(2000, 1, 1), SPLIT),
        ("TEST ", SPLIT, dt.date(2100, 1, 1)),
    ):
        h = {c: {x for x in ds if lo <= x < hi} for c, ds in sigs.items()}
        mm = simulate(
            by_code, dsex, signal_fn=lambda b, s=h: s.get(b[0].code, set()), max_pos=10, **ex
        )
        print(
            f"  {label}  {mm['total']:>+7.1f}%  vs index {idx(lo, hi):>+5.1f}%   trades {mm['n_trades']:>3}   win {mm['winrate']:.0f}%"
        )


if __name__ == "__main__":
    asyncio.run(_run())
