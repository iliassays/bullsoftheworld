"""Does rotating beat holding to exit? — test the user's 'miss a better stock' worry with data.

Baseline = hold every position to its own exit (+25% / -10% / 63d), never swap. Rotation = when the
book is full and a NEW signal's conviction beats your weakest holding's by more than a margin, sell
the weakest and buy the newcomer. We sweep the margin: a small margin rotates eagerly (churny), a
large one almost never. If rotation really captured 'better stocks', the rotating runs should beat
the baseline — net of the extra round-trip cost it pays. With a train/test split, because a rule
that only helps in-sample is just overfitting.

    uv run python scripts/rotation_study.py
"""

from __future__ import annotations

import asyncio
import datetime as dt

from portfolio_backtest import _load, simulate
from scheme2_value import _load_fundamentals
from scheme_lab import quality_reversal
from validate_ranking import _conviction_rank

SPLIT = dt.date(2025, 9, 1)
EXITS = dict(stop=-0.10, target=0.25, hold=63, max_pos=10)


def _rotations(m):
    return sum(1 for t in m["trade_log"] if t["reason"] == "rotate")


async def _run():
    by_code, dsex = await _load()
    fin, div = await _load_fundamentals("DSE")
    sigs = quality_reversal(by_code, fin, div)
    fn = lambda b: sigs.get(b[0].code, set())  # noqa: E731
    conv = _conviction_rank(by_code, fin, div)

    configs = [
        ("hold to exit (baseline)", None),
        ("rotate, margin 0.05 (eager)", 0.05),
        ("rotate, margin 0.10", 0.10),
        ("rotate, margin 0.20 (rare)", 0.20),
    ]

    print("Rotation = swap the weakest holding for a much higher-conviction new signal when full.")
    print("Baseline never swaps. Same Scheme-3 signals/exits/cost.\n")
    print(
        f"{'mode':<30}{'total%':>9}{'CAGR%':>8}{'maxDD%':>9}{'win%':>7}{'trades':>8}{'rotations':>11}"
    )
    print("-" * 82)
    for name, rot in configs:
        m = simulate(by_code, dsex, signal_fn=fn, rank_fn=conv, rotate=rot, **EXITS)
        print(
            f"{name:<30}{m['total']:>+9.1f}{m['cagr']:>+8.1f}{m['maxdd']:>9.1f}"
            f"{m['winrate']:>6.0f}%{m['n_trades']:>8}{_rotations(m):>11}"
        )

    def idx(lo, hi):
        v = [x for dd, x in sorted(dsex.items()) if lo <= dd < hi]
        return (v[-1] / v[0] - 1) * 100 if len(v) > 1 else 0

    print(f"\nOut-of-sample (split {SPLIT}) — does any benefit survive on unseen data?")
    for label, lo, hi in (
        ("TRAIN", dt.date(2000, 1, 1), SPLIT),
        ("TEST ", SPLIT, dt.date(2100, 1, 1)),
    ):
        half = {c: {x for x in ds if lo <= x < hi} for c, ds in sigs.items()}
        hfn = lambda b, h=half: h.get(b[0].code, set())  # noqa: E731
        print(f"  {label} (index {idx(lo, hi):+.1f}%):")
        for name, rot in configs:
            m = simulate(by_code, dsex, signal_fn=hfn, rank_fn=conv, rotate=rot, **EXITS)
            print(
                f"    {name:<30}{m['total']:>+8.1f}%   win {m['winrate']:>3.0f}%   rotations {_rotations(m):>3}"
            )


if __name__ == "__main__":
    asyncio.run(_run())
