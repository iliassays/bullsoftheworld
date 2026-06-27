"""Out-of-sample check for Scheme-3 (Quality Reversal) — defuse the "best of many" asterisk.

Scheme-3 was picked as the winner looking at the WHOLE 2 years, so some of its +74% could be luck.
Honest test: split the timeline in half. Run the exact same rule on each half independently. If the
edge shows up in BOTH the early period (when we'd have "discovered" it) and the later period (which it
then had no say in), it's structural. If it only works in one half, it's fragile.

    uv run python scripts/validate_scheme3.py

Same single-market-regime caveat applies — this checks stability across time, not across a crash.
"""

from __future__ import annotations

import asyncio
import datetime as dt

from portfolio_backtest import _load, simulate
from scheme2_value import _load_fundamentals
from scheme_lab import quality_reversal

SPLIT = dt.date(2025, 9, 1)  # ~midpoint of the active window
EXITS = dict(stop=-0.10, target=0.25, hold=63, max_pos=10)


def _restrict(sigs, lo, hi):
    return {c: {d for d in ds if lo <= d < hi} for c, ds in sigs.items()}


def _index_ret(dsex, lo, hi):
    ds = sorted(d for d in dsex if lo <= d < hi)
    return (dsex[ds[-1]] / dsex[ds[0]] - 1) * 100 if len(ds) > 1 else 0.0


def _report(name, m, dsex, lo, hi):
    n = m["n_trades"]
    span = ""
    if m["trade_log"]:
        ds = sorted(t["in_date"] for t in m["trade_log"])
        span = f"entries {ds[0]} .. {ds[-1]}"
    print(f"\n  {name}")
    print(f"    {span}")
    print(
        f"    1,000 -> {m['final']:,.0f}  ({m['total']:+.1f}%)   vs index {_index_ret(dsex, lo, hi):+.1f}%"
    )
    print(
        f"    trades {n}   win {m['winrate']:.0f}%   maxDD {m['maxdd']:.0f}%   avg W/L +{m['avg_win']:.0f}%/{m['avg_loss']:.0f}%"
    )


async def _run():
    by_code, dsex = await _load()
    fin, div = await _load_fundamentals("DSE")
    sigs = quality_reversal(by_code, fin, div)

    far_lo, far_hi = dt.date(2000, 1, 1), dt.date(2100, 1, 1)
    full = simulate(by_code, dsex, signal_fn=lambda b: sigs.get(b[0].code, set()), **EXITS)
    train_sigs = _restrict(sigs, far_lo, SPLIT)
    test_sigs = _restrict(sigs, SPLIT, far_hi)
    train = simulate(by_code, dsex, signal_fn=lambda b: train_sigs.get(b[0].code, set()), **EXITS)
    test = simulate(by_code, dsex, signal_fn=lambda b: test_sigs.get(b[0].code, set()), **EXITS)

    print(f"Scheme-3 Quality Reversal — out-of-sample split at {SPLIT}")
    _report(f"TRAIN  (entries before {SPLIT})", train, dsex, far_lo, SPLIT)
    _report(f"TEST   (entries on/after {SPLIT})", test, dsex, SPLIT, far_hi)
    _report("FULL   (both halves)", full, dsex, far_lo, far_hi)

    tw, tt = train["winrate"], test["winrate"]
    print("\n  Verdict:")
    print(f"    win-rate held? train {tw:.0f}% vs test {tt:.0f}%")
    both_positive = train["total"] > 0 and test["total"] > 0
    print(
        f"    positive in BOTH halves? {'YES — edge is stable across time' if both_positive else 'NO — concentrated/fragile'}"
    )


if __name__ == "__main__":
    asyncio.run(_run())
