"""Does size matter? Split the flagship's trades by market cap, and test a small-cap tilt.

Two questions: (1) where does Scheme-3's edge live — small, mid, or large caps? (2) does tilting the
strategy toward low-caps help or just add junk/manipulation risk? Splits the trade log by entry-time
market cap into terciles, then runs Scheme-3 restricted to each half of the universe.

    uv run python scripts/size_analysis.py

Caveat: market cap uses CURRENT shares outstanding (DSE bonus issues inflate share counts over time,
so historical caps are approximate — fine for small/large bucketing, not exact). Small-cap fills at
EOD close also overstate real tradability (wide spreads, manipulation). Read directionally.
"""

from __future__ import annotations

import asyncio
import statistics as st

from portfolio_backtest import _load, simulate
from scheme2_value import _load_fundamentals
from scheme_lab import quality_reversal
from sqlalchemy import select

from bulls.core.db import get_sessionmaker
from bulls.core.models import CompanyProfile

EXITS = dict(stop=-0.10, target=0.25, hold=63, max_pos=10)


async def _shares_and_cap(market):
    sm = get_sessionmaker()
    async with sm() as session:
        profs = list(
            await session.scalars(select(CompanyProfile).where(CompanyProfile.market == market))
        )
    shares = {p.code: p.outstanding_shares for p in profs if p.outstanding_shares}
    cap = {p.code: p.market_cap_mn for p in profs if p.market_cap_mn}
    return shares, cap


def _stats(trades):
    if not trades:
        return "  (none)"
    rets = [t["ret"] for t in trades]
    wins = [r for r in rets if r > 0]
    return (
        f"n {len(trades):>3}   win {len(wins) / len(trades) * 100:>3.0f}%   "
        f"avg {st.mean(rets):+5.1f}%   median {st.median(rets):+5.1f}%"
    )


async def _run():
    by_code, dsex = await _load()
    fin, div = await _load_fundamentals("DSE")
    shares, cap = await _shares_and_cap("DSE")
    sigs = quality_reversal(by_code, fin, div)

    # 1) split the flagship's trades by entry-time market cap
    m = simulate(by_code, dsex, signal_fn=lambda b: sigs.get(b[0].code, set()), **EXITS)
    trades = [t for t in m["trade_log"] if t["code"] in shares]
    for t in trades:
        t["mcap"] = t["in_px"] * shares[t["code"]] / 1e6  # Taka mn
    trades.sort(key=lambda t: t["mcap"])
    n = len(trades)
    third = n // 3
    buckets = [
        ("SMALL cap", trades[:third]),
        ("MID cap", trades[third : 2 * third]),
        ("LARGE cap", trades[2 * third :]),
    ]
    print(f"Scheme-3 trades by entry market cap ({n} trades with cap data):")
    for name, b in buckets:
        if b:
            lo, hi = b[0]["mcap"], b[-1]["mcap"]
            print(f"  {name:<10} [{lo:>8,.0f} to {hi:>9,.0f} mn]   {_stats(b)}")

    # 2) restrict the strategy to small vs large half of the universe (by latest market cap)
    if cap:
        med = st.median(cap.values())
        small = {c for c, v in cap.items() if v < med}
        large = {c for c, v in cap.items() if v >= med}
        print(f"\nStrategy restricted by universe size (median cap {med:,.0f} mn):")
        print(f"  {'VARIANT':<22}{'total%':>9}{'maxDD%':>9}{'trades':>8}{'win%':>7}")
        print("  " + "-" * 54)
        def restricted(keep):
            def fn(b):
                return sigs.get(b[0].code, set()) if (keep is None or b[0].code in keep) else set()
            return fn

        for label, keep in (
            ("all names", None),
            ("small-cap only", small),
            ("large-cap only", large),
        ):
            mm = simulate(by_code, dsex, signal_fn=restricted(keep), **EXITS)
            print(
                f"  {label:<22}{mm['total']:>+9.1f}{mm['maxdd']:>9.1f}{mm['n_trades']:>8}{mm['winrate']:>6.0f}%"
            )


if __name__ == "__main__":
    asyncio.run(_run())
