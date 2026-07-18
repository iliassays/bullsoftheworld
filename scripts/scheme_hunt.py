"""Legacy scheme hunt: low-vol, multi-factor and quality-momentum diagnostics.

Builds a cross-sectional engine that sees BOTH fundamentals and price features (volatility, 52w
position, 3-month momentum) at each rebalance, then tests strategies the earlier labs couldn't:
  - low-vol quality        (the low-volatility anomaly: calm + cheap + profitable)
  - multi-factor composite (AQR-style: rank value + quality + reversal together, buy the top)
  - quality momentum       (does momentum work when restricted to cheap profitable names?)
  - value-reversal x-sec   (the most beaten-down cheap profitable names, monthly, long hold)
These variants were exploratory and create multiple-comparison risk. They are preserved for research
memory, not as an active strategy search or a comparison with the stale Scheme-3 headline.

    uv run python scripts/scheme_hunt.py
"""

from __future__ import annotations

import asyncio
import statistics as st
from collections import defaultdict

from portfolio_backtest import MIN_AVG_VOL, _load, dsex_return, simulate
from scheme2_value import _fundamentals_at, _load_fundamentals, _pct
from schemes import _roll_ext

TOP_N = 12


def _prep(by_code):
    liquid = {
        c: b for c, b in by_code.items() if sum(x.volume for x in b[-20:]) / 20 >= MIN_AVG_VOL
    }
    prepped = {}
    for c, bars in liquid.items():
        closes = [b.close for b in bars]
        prepped[c] = {
            "dates": [b.date for b in bars],
            "closes": closes,
            "didx": {b.date: i for i, b in enumerate(bars)},
            "hi": _roll_ext([b.high for b in bars], 252, True),
            "lo": _roll_ext([b.low for b in bars], 252, False),
        }
    return prepped


def _feature_row(p, i, code, year, fin, div):
    """Price + fundamental features for one code at bar index i; None if unqualified."""
    fa = _fundamentals_at(code, p["closes"][i], year, fin, div)
    if not fa or i < 64:
        return None
    pe, pb, roe, epsg, cons = fa
    closes, hi, lo = p["closes"], p["hi"][i], p["lo"][i]
    if not hi or hi <= lo:
        return None
    rets = [closes[j] / closes[j - 1] - 1 for j in range(i - 60, i) if closes[j - 1]]
    vol = st.pstdev(rets) * (252**0.5) * 100 if len(rets) > 2 else None
    pos52 = (closes[i] - lo) / (hi - lo) * 100
    mom3 = (closes[i] / closes[i - 63] - 1) * 100 if closes[i - 63] else None
    return {
        "pe": pe,
        "pb": pb,
        "roe": roe,
        "epsg": epsg,
        "cons": cons,
        "vol": vol,
        "pos52": pos52,
        "mom3": mom3,
    }


def _run_cross(prepped, dsex, fin, div, score_fn, exits, by_code):
    axis = sorted({d for p in prepped.values() for d in p["dates"]})
    signals = defaultdict(set)
    for k in range(80, len(axis), 21):
        d = axis[k]
        rows = {}
        for code, p in prepped.items():
            i = p["didx"].get(d)
            if i is None:
                continue
            r = _feature_row(p, i, code, d.year, fin, div)
            if r:
                rows[code] = r
        if len(rows) < 20:
            continue
        scores = score_fn(rows)
        for code in sorted(scores, key=lambda c: scores[c], reverse=True)[:TOP_N]:
            signals[code].add(d)
    return simulate(by_code, dsex, signal_fn=lambda b: signals.get(b[0].code, set()), **exits)


def _rk(rows, key, reverse=False):
    return _pct([(c, v[key]) for c, v in rows.items() if v[key] is not None], reverse=reverse)


def _avg(*ranks):
    def f(code):
        vals = [r.get(code) for r in ranks if r.get(code) is not None]
        return sum(vals) / len(vals) if vals else 0

    return f


def low_vol_quality(rows):
    cheap = _avg(_rk(rows, "pe", True), _rk(rows, "pb", True))
    qual = _avg(_rk(rows, "roe"), _rk(rows, "epsg"))
    lowvol = _rk(rows, "vol", True)
    return {c: cheap(c) + qual(c) + lowvol.get(c, 0) for c in rows}


def multifactor(rows):
    value = _avg(_rk(rows, "pe", True), _rk(rows, "pb", True))
    qual = _avg(_rk(rows, "roe"), _rk(rows, "epsg"), _rk(rows, "cons"))
    reversal = _rk(rows, "pos52", True)  # nearer 52w low scores higher
    return {c: value(c) + qual(c) + reversal.get(c, 0) for c in rows}


def quality_momentum(rows):
    qual = _avg(_rk(rows, "roe"), _rk(rows, "epsg"))
    mom = _avg(_rk(rows, "mom3"), _rk(rows, "pos52"))  # higher momentum / nearer highs
    cheapish = _rk(rows, "pe", True)
    return {c: qual(c) + mom(c) + cheapish.get(c, 0) for c in rows}


def value_reversal_xsec(rows):
    value = _avg(_rk(rows, "pe", True), _rk(rows, "pb", True))
    reversal = _rk(rows, "pos52", True)
    qual = _rk(rows, "roe")
    return {c: value(c) + reversal.get(c, 0) + qual.get(c, 0) for c in rows}


LONG = dict(stop=-0.15, target=0.50, hold=180, max_pos=12)
MED = dict(stop=-0.12, target=0.35, hold=90, max_pos=12)
SCHEMES = [
    ("low-vol quality", low_vol_quality, LONG),
    ("multi-factor composite", multifactor, LONG),
    ("quality momentum", quality_momentum, MED),
    ("value-reversal x-sec", value_reversal_xsec, LONG),
]


async def _run():
    by_code, dsex = await _load()
    fin, div = await _load_fundamentals("DSE")
    prepped = _prep(by_code)
    index_return = dsex_return(dsex)
    print(f"Cross-sectional engine · {len(prepped)} liquid names · monthly rebalance, top-{TOP_N}")
    print(f"Full-window DSEX price return: {index_return:+.1f}%")
    print("Legacy Scheme-3 headline omitted; it used a separate optimistic methodology.\n")
    print(
        f"{'NEW SCHEME':<24}{'total%':>9}{'CAGR%':>8}{'maxDD%':>9}{'trades':>8}{'win%':>7}{'vs idx':>8}"
    )
    print("-" * 76)
    results = []
    for name, fn, exits in SCHEMES:
        m = _run_cross(prepped, dsex, fin, div, fn, exits, by_code)
        results.append((name, m))
    for name, m in sorted(results, key=lambda r: r[1]["total"], reverse=True):
        print(
            f"{name:<24}{m['total']:>+9.1f}{m['cagr']:>+8.1f}{m['maxdd']:>9.1f}"
            f"{m['n_trades']:>8}{m['winrate']:>6.0f}%{m['total'] - index_return:>+8.1f}"
        )


if __name__ == "__main__":
    asyncio.run(_run())
