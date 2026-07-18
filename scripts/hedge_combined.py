"""Legacy two-sleeve diagnostic — Scheme-3 bounce plus Scheme-2 quality hold.

This preserves an exploratory blend of two legacy simulated equity streams. It does not establish
that either rule is an edge, that the sleeves are independent, or that an executable fund exists.

    uv run python scripts/hedge_combined.py
"""

from __future__ import annotations

import asyncio

from portfolio_backtest import START, _load, dsex_return, simulate
from scheme2_value import _build_signals as scheme2_signals
from scheme2_value import _load_fundamentals
from scheme_lab import quality_reversal

S3_EXITS = dict(stop=-0.10, target=0.25, hold=63, max_pos=10)
S2_EXITS = dict(stop=-0.15, target=0.50, hold=180, max_pos=12)


def _maxdd(curve):
    peak, mdd = curve[0], 0.0
    for e in curve:
        peak = max(peak, e)
        mdd = min(mdd, e / peak - 1)
    return mdd * 100


def _stats(eq, years):
    total = (eq[-1] / START - 1) * 100
    return total, ((eq[-1] / START) ** (1 / years) - 1) * 100, _maxdd(eq)


async def _run():
    by_code, dsex = await _load()
    index_return = dsex_return(dsex)
    fin, div = await _load_fundamentals("DSE")
    s3 = quality_reversal(by_code, fin, div)
    s2 = scheme2_signals(by_code, fin, div)

    m3 = simulate(by_code, dsex, signal_fn=lambda b: s3.get(b[0].code, set()), **S3_EXITS)
    m2 = simulate(by_code, dsex, signal_fn=lambda b: s2.get(b[0].code, set()), **S2_EXITS)
    c3 = [e for _, e in m3["curve"]]
    c2 = [e for _, e in m2["curve"]]
    n = min(len(c3), len(c2))
    c3, c2 = c3[-n:], c2[-n:]
    dates = [d for d, _ in m3["curve"]][-n:]
    years = (dates[-1] - dates[0]).days / 365

    print("Legacy two-sleeve diagnostic — Scheme-3 + Scheme-2")
    print(f"Reference — full-window DSEX price return: {index_return:+.1f}%\n")
    print(f"{'ALLOCATION':<26}{'total%':>9}{'CAGR%':>8}{'maxDD%':>9}{'1,000 ->':>10}")
    print("-" * 62)
    blends = [
        ("100% Scheme-3 only", 1.0),
        ("70% S3 / 30% S2", 0.7),
        ("60% S3 / 40% S2", 0.6),
        ("50% / 50%", 0.5),
        ("100% Scheme-2 only", 0.0),
    ]
    for label, w3 in blends:
        eq = [w3 * a + (1 - w3) * b for a, b in zip(c3, c2, strict=True)]
        total, cagr, mdd = _stats(eq, years)
        print(f"{label:<26}{total:>+9.1f}{cagr:>+8.1f}{mdd:>9.1f}{eq[-1]:>10,.0f}")
    print(
        "\nA smoother legacy curve is only a hypothesis; it is not evidence of executable diversification"
    )
    print(
        "without point-in-time data, independent sleeves and an institutional portfolio simulation."
    )


if __name__ == "__main__":
    asyncio.run(_run())
