"""Momentum pullback to the 9-EMA + bounce (daily-swing analogue of the user's intraday setup).

The idea: a stock in an uptrend dips back to its 9-EMA and bounces for the next leg up — taken only
while it trades above its volume-weighted average price. VWAP is an INTRADAY concept (resets each
session, needs minute data), which we don't have here — so this is the DAILY analogue: a 20-day
ROLLING VWAP stands in for "above the volume-weighted average," and the 9-EMA is the daily 9-EMA.
The true 1-minute 9-EMA/session-VWAP version needs the titan_platform intraday data.

Tests the rule with and without the VWAP filter, a couple of trend definitions, and momentum-style
exits, against buy and hold, with a train/test split so we do not reuse the old Scheme-3 headline
ourselves. DSE history said plain momentum loses — but a pullback-continuation entry is a different
animal, so it's worth a clean look.

    uv run python scripts/momentum_pullback.py
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections import defaultdict

from portfolio_backtest import MIN_AVG_VOL, _load, dsex_return, simulate

SPLIT = dt.date(2025, 9, 1)


def _ema(vals, n):
    k = 2 / (n + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def _roll_vwap(bars, n):
    tp = [(b.high + b.low + b.close) / 3 for b in bars]
    vol = [float(b.volume) for b in bars]
    out = [None] * len(bars)
    for i in range(len(bars)):
        lo = max(0, i - n + 1)
        sv = sum(vol[lo : i + 1])
        out[i] = sum(tp[j] * vol[j] for j in range(lo, i + 1)) / sv if sv else None
    return out


def _signals(by_code, require_vwap):
    sigs = defaultdict(set)
    for code, bars in by_code.items():
        if sum(x.volume for x in bars[-20:]) / 20 < MIN_AVG_VOL or len(bars) < 80:
            continue
        c = [b.close for b in bars]
        ema9, ema21 = _ema(c, 9), _ema(c, 21)
        vwap = _roll_vwap(bars, 20)
        for i in range(63, len(bars)):
            up = c[i] > c[i - 63] and ema9[i] > ema21[i]  # in momentum + short-term uptrend
            prior_above = c[i - 1] > ema9[i - 1]  # was riding above the 9-EMA
            dipped = bars[i].low <= ema9[i]  # today's pullback touched the 9-EMA
            bounce = c[i] > ema9[i] and c[i] > bars[i].open  # closed back above it, green
            vwap_ok = (not require_vwap) or (vwap[i] is not None and c[i] > vwap[i])
            if up and prior_above and dipped and bounce and vwap_ok:
                sigs[code].add(bars[i].date)
    return sigs


async def _run():
    by_code, dsex = await _load()
    sig_v = _signals(by_code, require_vwap=True)
    sig_n = _signals(by_code, require_vwap=False)

    def idx(lo, hi):
        v = [x for dd, x in sorted(dsex.items()) if lo <= dd < hi]
        return (v[-1] / v[0] - 1) * 100 if len(v) > 1 else 0

    configs = [
        ("trail 10% / hold 60d", dict(stop=-0.10, trail=0.10, hold=60)),
        ("fixed +15% / -8% / 40d", dict(stop=-0.08, target=0.15, hold=40)),
        ("trail 8% / hold 40d", dict(stop=-0.08, trail=0.08, hold=40)),
    ]
    print("9-EMA pullback + bounce (daily). 'VWAP' = 20-day rolling VWAP filter (intraday proxy).")
    print(f"Reference — full-window DSEX price return: {dsex_return(dsex):+.1f}%")
    print("Legacy Scheme-3 headline omitted; it used a separate optimistic methodology.\n")
    print(
        f"{'exit rule':<24}{'filter':<10}{'total%':>9}{'CAGR%':>8}{'maxDD%':>9}{'win%':>7}{'trades':>8}"
    )
    print("-" * 75)
    best = None
    for name, ex in configs:
        for label, sg in (("+VWAP", sig_v), ("no VWAP", sig_n)):
            m = simulate(
                by_code, dsex, signal_fn=lambda b, s=sg: s.get(b[0].code, set()), max_pos=10, **ex
            )
            print(
                f"{name:<24}{label:<10}{m['total']:>+9.1f}{m['cagr']:>+8.1f}"
                f"{m['maxdd']:>9.1f}{m['winrate']:>6.0f}%{m['n_trades']:>8}"
            )
            if best is None or m["total"] > best[1]["total"]:
                best = (f"{name} {label}", m, ex, sg)

    name, _m, ex, sg = best
    print(f"\nOut-of-sample check on the best ({name}), split {SPLIT}:")
    for label, lo, hi in (
        ("TRAIN", dt.date(2000, 1, 1), SPLIT),
        ("TEST ", SPLIT, dt.date(2100, 1, 1)),
    ):
        half = {c: {x for x in ds if lo <= x < hi} for c, ds in sg.items()}
        mm = simulate(
            by_code, dsex, signal_fn=lambda b, h=half: h.get(b[0].code, set()), max_pos=10, **ex
        )
        print(
            f"  {label}  {mm['total']:>+7.1f}%  vs index {idx(lo, hi):>+5.1f}%   trades {mm['n_trades']:>3}   win {mm['winrate']:.0f}%"
        )


if __name__ == "__main__":
    asyncio.run(_run())
