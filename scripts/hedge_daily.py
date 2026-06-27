"""Hedge — your daily morning list (Scheme-3 Quality Reversal, the validated flagship).

What to check each morning. Scans the latest EOD data for names that just FIRED the flagship signal —
a washed-out, profitable, cheap company turning up — and prints each with entry / stop / target / hold
and the quality context (P/E, ROE, sector). Also a WATCHLIST: names set up in the zone, waiting only
for the breakout trigger.

    uv run python scripts/hedge_daily.py            # fired in last 5 sessions + watchlist
    uv run python scripts/hedge_daily.py --days 1   # only today

Scheme-3 (backtested, out-of-sample validated): ~58% win, winners ~2.3x losers, +74% / 2yr vs index
+8%, ~12% worst drawdown. EOD/delayed data, single market regime — trade small, a stop is mandatory.
"""

from __future__ import annotations

import argparse
import asyncio

from portfolio_backtest import MIN_AVG_VOL, WARMUP, _load
from scheme2_value import _fundamentals_at, _load_fundamentals
from schemes import _prep
from sqlalchemy import select

from bulls.core.db import get_sessionmaker
from bulls.core.models import CompanyProfile

STOP, TARGET = -0.10, 0.25
MAX_PE = 25  # quality gate: profitable and not expensive


async def _profiles(market):
    sm = get_sessionmaker()
    async with sm() as session:
        profs = list(
            await session.scalars(select(CompanyProfile).where(CompanyProfile.market == market))
        )
    return {p.code: p for p in profs}


def _qualifies(code, price, year, fin, div):
    """Returns (pe, roe) if profitable + cheap (the Scheme-3 quality gate), else None."""
    fa = _fundamentals_at(code, price, year, fin, div)
    if fa and fa[0] <= MAX_PE:  # fa = (pe, pb, roe, epsg, cons)
        return fa[0], fa[2]
    return None


async def _run(days):
    by_code, _ = await _load()
    fin, div = await _load_fundamentals("DSE")
    profs = await _profiles("DSE")
    latest = max(b.date for bars in by_code.values() for b in bars)

    fired, watch = [], []
    for code, bars in by_code.items():
        if len(bars) < WARMUP + 5 or sum(x.volume for x in bars[-20:]) / 20 < MIN_AVG_VOL:
            continue
        if (latest - bars[-1].date).days > 10:  # stale/delisted
            continue
        c, h, _r, _s20, _s200, _v20, hi, lo = _prep(bars)
        i = len(bars) - 1
        if not hi[i] or hi[i] <= lo[i]:
            continue
        below = (c[i] / hi[i] - 1) * 100
        pos = (c[i] - lo[i]) / (hi[i] - lo[i]) * 100
        if not (below < -40 and pos < 15):  # not in the launch zone today
            continue
        q = _qualifies(code, c[i], latest.year, fin, div)
        if not q:  # not profitable/cheap — Scheme-3 skips it (this is what saves us from junk)
            continue
        pe, roe = q
        sector = (profs.get(code).sector if profs.get(code) else None) or "?"
        # did the breakout trigger fire within the look-back window?
        fired_on = next(
            (
                bars[j].date
                for j in range(len(bars) - days, len(bars))
                if j >= 5 and c[j] > max(h[j - 5 : j])
            ),
            None,
        )
        row = (code, c[i], pe, roe, below, pos, sector, fired_on)
        (fired if fired_on else watch).append(row)

    print(f"HEDGE — daily list · as of EOD {latest} · EOD/delayed · stop is mandatory\n")
    print(f"=== BUY signals (fired in last {days} session(s)): {len(fired)} ===")
    if fired:
        print(
            f"  {'CODE':<11}{'entry':>8}{'stop':>8}{'target':>8}{'P/E':>6}{'ROE':>6}  {'why / sector'}"
        )
        for code, px, pe, roe, below, _pos, sector, _fon in sorted(
            fired, key=lambda r: r[-1], reverse=True
        ):
            print(
                f"  {code:<11}{px:>8.1f}{px * (1 + STOP):>8.1f}{px * (1 + TARGET):>8.1f}"
                f"{pe:>6.1f}{roe:>5.0f}%  washed-out {below:>3.0f}%, cheap+profitable · {sector[:18]}"
            )
    else:
        print("  (none today — the flagship is selective; see the watchlist)")

    print(f"\n=== WATCHLIST (zone + quality, waiting for the breakout): {len(watch)} ===")
    print(f"  {'CODE':<11}{'price':>8}{'P/E':>6}{'ROE':>6}{'below_hi':>10}  sector")
    for code, px, pe, roe, below, _pos, sector, _f in sorted(watch, key=lambda r: r[4]):
        print(f"  {code:<11}{px:>8.1f}{pe:>6.1f}{roe:>5.0f}%{below:>9.0f}%  {sector[:18]}")

    print(
        "\nHold ~2 weeks to 3 months (exit at +25% target, -10% stop, or 3 months). Risk ~1-2% of "
        "capital per name; ~10 positions. Low-cap names: size down (fills are rough)."
    )


def main():
    ap = argparse.ArgumentParser(
        description="Hedge daily morning list (Scheme-3 Quality Reversal)."
    )
    ap.add_argument("--days", type=int, default=5, help="look-back window for a fired breakout")
    asyncio.run(_run(ap.parse_args().days))


if __name__ == "__main__":
    main()
