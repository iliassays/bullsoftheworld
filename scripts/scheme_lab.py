"""Legacy Scheme lab v2 — exploratory hybrids of reversal and quality/value rules.

The original study combined rules that looked favorable in one sample. Its same-close engine and
multiple strategy search are preserved for reproducibility, not treated as proof or Atlas admission.

    uv run python scripts/scheme_lab.py
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

from portfolio_backtest import MIN_AVG_VOL, WARMUP, _load, dsex_return, simulate
from scheme2_value import _build_signals as scheme2_signals
from scheme2_value import _fundamentals_at, _load_fundamentals, _pct
from schemes import _prep


def _liquid(by_code):
    return {c: b for c, b in by_code.items() if sum(x.volume for x in b[-20:]) / 20 >= MIN_AVG_VOL}


# ---- hybrid (price trigger + fundamental gate), scanned per stock per day ----
def quality_reversal(by_code, fin, div):
    """Scheme-3: Scheme-1's washout-bounce, but ONLY on profitable, not-expensive names (P/E<=25)."""
    sigs = defaultdict(set)
    for code, bars in _liquid(by_code).items():
        c, h, _r, _s20, _s200, _v20, hi, lo = _prep(bars)
        for i in range(WARMUP, len(bars)):
            if not c[i] or not hi[i] or hi[i] <= lo[i]:
                continue
            below = (c[i] / hi[i] - 1) * 100
            pos = (c[i] - lo[i]) / (hi[i] - lo[i]) * 100
            if below < -40 and pos < 15 and c[i] > max(h[i - 5 : i]):
                fa = _fundamentals_at(code, c[i], bars[i].date.year, fin, div)
                if fa and fa[0] <= 25:
                    sigs[code].add(bars[i].date)
    return sigs


def cheap_oversold(by_code, fin, div):
    """Scheme-4: cheap profitable name (P/E<=20) turning up from oversold (RSI crosses 35)."""
    sigs = defaultdict(set)
    for code, bars in _liquid(by_code).items():
        c, _h, rsi, *_ = _prep(bars)
        for i in range(WARMUP, len(bars)):
            if rsi[i - 1] is None or rsi[i] is None or not (rsi[i - 1] < 35 <= rsi[i]):
                continue
            fa = _fundamentals_at(code, c[i], bars[i].date.year, fin, div)
            if fa and fa[0] <= 20:
                sigs[code].add(bars[i].date)
    return sigs


# ---- cross-sectional monthly (rank the universe, buy top-N) ----
def _cross_monthly(by_code, fin, div, score_fn, top_n=12):
    liquid = _liquid(by_code)
    close_on = {c: {b.date: b.close for b in bb} for c, bb in liquid.items()}
    axis = sorted({b.date for bb in liquid.values() for b in bb})
    sigs = defaultdict(set)
    for k in range(80, len(axis), 21):
        d = axis[k]
        rows = {}
        for code in liquid:
            price = close_on[code].get(d)
            if not price:
                continue
            fa = _fundamentals_at(code, price, d.year, fin, div)
            if fa:
                rows[code] = fa
        if len(rows) < 20:
            continue
        scores = score_fn(rows)
        for code in sorted(scores, key=lambda c: scores[c], reverse=True)[:top_n]:
            sigs[code].add(d)
    return sigs


def magic_formula(by_code, fin, div):
    """Scheme-5: Greenblatt — rank by earnings yield (1/PE) + ROE, buy the top (cheap + quality)."""

    def score(rows):  # rows[code] = (pe, pb, roe, epsg, cons)
        ey = _pct([(c, 1 / v[0]) for c, v in rows.items()])
        roe = _pct([(c, v[2]) for c, v in rows.items()])
        return {c: ey.get(c, 0) + roe.get(c, 0) for c in rows}

    return _cross_monthly(by_code, fin, div, score)


def deep_growth_value(by_code, fin, div):
    """Scheme-6: cheap (low P/E) + genuinely growing earnings (high EPS growth), monthly top-N."""

    def score(rows):
        pe = _pct([(c, v[0]) for c, v in rows.items()], reverse=True)
        eg = _pct([(c, v[3]) for c, v in rows.items() if v[3] is not None])
        return {c: (pe.get(c, 0) + eg.get(c, 0)) for c in rows}

    return _cross_monthly(by_code, fin, div, score)


SCHEMES = [
    ("1 deep-value reversal", None, dict(stop=-0.10, target=0.25, hold=63, max_pos=10)),
    ("2 quality-value", scheme2_signals, dict(stop=-0.15, target=0.50, hold=180, max_pos=12)),
    ("3 quality reversal", quality_reversal, dict(stop=-0.10, target=0.25, hold=63, max_pos=10)),
    ("4 cheap + oversold", cheap_oversold, dict(stop=-0.12, target=0.30, hold=90, max_pos=10)),
    ("5 magic formula", magic_formula, dict(stop=-0.15, target=0.50, hold=180, max_pos=12)),
    ("6 deep growth-value", deep_growth_value, dict(stop=-0.15, target=0.50, hold=180, max_pos=12)),
]


async def _run():
    by_code, dsex = await _load()
    index_return = dsex_return(dsex)
    fin, div = await _load_fundamentals("DSE")
    print("Each scheme: own entry rule, style-appropriate exits, same engine/costs.")
    print(f"Reference — full-window DSEX price return: {index_return:+.1f}%\n")
    print(
        f"{'SCHEME':<24}{'total%':>9}{'CAGR%':>8}{'maxDD%':>9}{'trades':>8}{'win%':>7}{'avg W/L':>12}{'vs idx':>8}"
    )
    print("-" * 86)
    results = []
    for name, builder, exits in SCHEMES:
        sigs = (
            builder(by_code, fin, div) if builder else None
        )  # None -> default Scheme-1 in simulate
        fn = (lambda b, s=sigs: s.get(b[0].code, set())) if sigs is not None else None
        m = simulate(by_code, dsex, signal_fn=fn, **exits)
        results.append((name, m))
    for name, m in sorted(results, key=lambda r: r[1]["total"], reverse=True):
        wl = f"+{m['avg_win']:.0f}/{m['avg_loss']:.0f}"
        print(
            f"{name:<24}{m['total']:>+9.1f}{m['cagr']:>+8.1f}{m['maxdd']:>9.1f}"
            f"{m['n_trades']:>8}{m['winrate']:>6.0f}%{wl:>12}{m['total'] - index_return:>+8.1f}"
        )


if __name__ == "__main__":
    asyncio.run(_run())
