"""Two-sleeve Hedge — Scheme-3 (active bounce) + Scheme-2 (calm quality-hold) in one account.

The durable-compounding idea: split capital across two uncorrelated edges so cash is always working
and the ride is smoother than either alone. Each sleeve runs its own rules/exits; we blend their
equity streams at a few weights and compare to the single sleeve and the index.

    uv run python scripts/hedge_combined.py
"""

from __future__ import annotations

import asyncio

from portfolio_backtest import START, _load, simulate
from scheme2_value import _build_signals as scheme2_signals
from scheme2_value import _load_fundamentals
from scheme_lab import quality_reversal

INDEX = 7.8
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

    print("Two-sleeve Hedge — Scheme-3 (active) + Scheme-2 (calm hold)")
    print(f"Reference — buy & hold DSEX: +{INDEX}%\n")
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
        tag = "  <- flagship" if w3 == 1.0 else ""
        print(f"{label:<26}{total:>+9.1f}{cagr:>+8.1f}{mdd:>9.1f}{eq[-1]:>10,.0f}{tag}")
    print(
        "\nThe point isn't a bigger number — it's a SMOOTHER one: a blend should cut the drawdown"
    )
    print(
        "below either sleeve while keeping most of the return, because the two edges don't move together."
    )


if __name__ == "__main__":
    asyncio.run(_run())
