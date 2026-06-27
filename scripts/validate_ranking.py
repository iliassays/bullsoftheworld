"""Validate the conviction ranking — is 'fund the strongest first' as good as the tested order?

The daily list now ranks signals by a conviction score (washout + cheapness + ROE) so that, on days
when more names fire than you have free slots, you fund the best first. But the +74% backtest filled
those contested slots ALPHABETICALLY (an arbitrary tie-break). Before trusting conviction live, we
check it on the same engine: does conviction-first beat / match / lose to alphabetical?

We test three orderings (conviction-first, alphabetical = current, WORST-first) at the real cap
(10 positions) and a stressed cap (5 positions, where slot scarcity bites hardest and ordering
matters most), with a train/test split. The conviction rank is reconstructed point-in-time, exactly
as the live score is computed.

    uv run python scripts/validate_ranking.py
"""

from __future__ import annotations

import asyncio
import datetime as dt

from portfolio_backtest import WARMUP, _load, simulate
from scheme2_value import _fundamentals_at, _load_fundamentals
from scheme_lab import quality_reversal
from schemes import _prep

SPLIT = dt.date(2025, 9, 1)


def _conviction_rank(by_code, fin, div):
    """Build rank_fn(code, date) -> 0..1 conviction, identical to the live daily-list score."""
    px, below = {}, {}  # px[code][date]=close ; below[code][date]=% off the 1-year high
    for code, bars in by_code.items():
        c, _h, _r, _s20, _s200, _v20, hi, lo = _prep(bars)
        pm, bm = {}, {}
        for i in range(WARMUP, len(bars)):
            if c[i] and hi[i] and hi[i] > lo[i]:
                pm[bars[i].date] = c[i]
                bm[bars[i].date] = (c[i] / hi[i] - 1) * 100
        px[code], below[code] = pm, bm

    def rank(code, d):
        price = px.get(code, {}).get(d)
        b = below.get(code, {}).get(d)
        if price is None or b is None:
            return -1.0
        fa = _fundamentals_at(code, price, d.year, fin, div)
        if not fa:
            return -1.0
        pe, _pb, roe, *_ = fa
        washout = min(abs(b), 80) / 80
        cheap = max(0.0, (25 - min(pe, 25)) / 25)
        qual = min(max(roe, 0), 30) / 30
        return (washout + cheap + qual) / 3

    return rank


async def _run():
    by_code, dsex = await _load()
    fin, div = await _load_fundamentals("DSE")
    sigs = quality_reversal(by_code, fin, div)
    fn = lambda b: sigs.get(b[0].code, set())  # noqa: E731
    conv = _conviction_rank(by_code, fin, div)
    exits = dict(stop=-0.10, target=0.25, hold=63)

    orderings = [
        ("conviction-first (new)", conv),
        ("alphabetical (tested)", None),
        ("WORST-first (sanity)", lambda c, d: -conv(c, d)),
    ]

    def idx(lo, hi):
        v = [x for dd, x in sorted(dsex.items()) if lo <= dd < hi]
        return (v[-1] / v[0] - 1) * 100 if len(v) > 1 else 0

    for cap in (10, 5):
        print(
            f"\n=== max {cap} positions {'(real)' if cap == 10 else '(stressed — scarcity bites)'} ==="
        )
        print(f"{'slot order':<26}{'total%':>9}{'CAGR%':>8}{'maxDD%':>9}{'win%':>7}{'trades':>8}")
        print("-" * 67)
        for name, rf in orderings:
            m = simulate(by_code, dsex, signal_fn=fn, rank_fn=rf, max_pos=cap, **exits)
            print(
                f"{name:<26}{m['total']:>+9.1f}{m['cagr']:>+8.1f}{m['maxdd']:>9.1f}"
                f"{m['winrate']:>6.0f}%{m['n_trades']:>8}"
            )

    print(f"\n=== out-of-sample (max 5, where ordering matters most) · split {SPLIT} ===")
    for label, lo, hi in (
        ("TRAIN", dt.date(2000, 1, 1), SPLIT),
        ("TEST ", SPLIT, dt.date(2100, 1, 1)),
    ):
        half = {c: {x for x in ds if lo <= x < hi} for c, ds in sigs.items()}
        hfn = lambda b, h=half: h.get(b[0].code, set())  # noqa: E731
        print(f"  {label} (index {idx(lo, hi):+.1f}%):")
        for name, rf in orderings:
            m = simulate(by_code, dsex, signal_fn=hfn, rank_fn=rf, max_pos=5, **exits)
            print(
                f"    {name:<26}{m['total']:>+8.1f}%   win {m['winrate']:>3.0f}%   trades {m['n_trades']:>3}"
            )


if __name__ == "__main__":
    asyncio.run(_run())
