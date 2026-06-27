"""Precursor study — what does a stock's base look like JUST BEFORE it launches?

Goal: catch the move early. For every liquid name we find its launch point (the trough it later
rallied from), measure the base in the ~40 days leading INTO that trough (volume build, accumulation,
compression, drawdown depth, RSI), then split names by how far they ran afterward and compare the
groups. If the big-runners share a base signature the quiet names lack, that's an early-entry edge.

    uv run python scripts/precursor_study.py

Honesty: bars only (volume + price structure). Ownership can't be a historical precursor here
(~3 snapshots/stock) — it's a live confirmation overlay, not part of this study. 2-year, single-regime
window: a signature here is a lead to validate, not a proven system. No deep model — too little data.
"""

from __future__ import annotations

import asyncio
import statistics as st
from collections import defaultdict

from sqlalchemy import select

from bulls.core.db import get_sessionmaker
from bulls.core.models import DailyBar

MARKET = "DSE"
MIN_AVG_VOL = 5_000
SEARCH_LO, SEARCH_HI = 200, 70  # find the launch trough within bars[-200:-70] (leaves forward room)
FWD = 60  # trading days forward to measure the run
BIG_RUN = 60.0  # % trough->peak that counts as a "launch"
QUIET_RUN = 20.0  # % below which it's a non-event (control group)


async def _load() -> dict[str, list[DailyBar]]:
    sm = get_sessionmaker()
    async with sm() as session:
        bars = list(
            await session.scalars(
                select(DailyBar)
                .where(DailyBar.market == MARKET)
                .order_by(DailyBar.code, DailyBar.date)
            )
        )
    by_code: dict[str, list[DailyBar]] = defaultdict(list)
    for b in bars:
        by_code[b.code].append(b)
    return by_code


def _features(bars: list[DailyBar], t: int) -> dict | None:
    """Base signature measured in the window ending at the launch trough index t."""
    if t < 90 or t + FWD >= len(bars):
        return None
    closes = [b.close for b in bars]
    vols = [b.volume for b in bars]
    base = slice(t - 20, t)  # 20d leading into the trough
    prior = slice(t - 60, t - 20)  # the 40d before that (baseline)
    base_vol = st.mean(vols[base]) or 1
    prior_vol = st.mean(vols[prior]) or 1
    long_vol = st.mean(vols[t - 90 : t - 10]) or 1
    rets = [closes[i] / closes[i - 1] - 1 for i in range(t - 30, t) if closes[i - 1]]
    up_vol = sum(vols[i] for i in range(t - 20, t) if closes[i] >= closes[i - 1])
    tot_vol = sum(vols[i] for i in range(t - 20, t)) or 1
    hi_252 = max(b.high for b in bars[max(0, t - 252) : t + 1])
    lo_252 = min(b.low for b in bars[max(0, t - 252) : t + 1])
    fwd_peak = max(b.high for b in bars[t + 1 : t + 1 + FWD])
    run = (fwd_peak / closes[t] - 1) * 100 if closes[t] else 0.0
    return {
        "vol_surge": base_vol / prior_vol,  # volume building into the low (>1 = accumulation)
        "vol_vs_long": base_vol / long_vol,  # recent vs longer baseline
        "up_vol_share": up_vol / tot_vol,  # share of base volume on up-days (>0.5 = accumulation)
        "compression": st.pstdev(rets) * 100
        if len(rets) > 2
        else 0.0,  # daily-return stdev %, lower = coiled
        "drawdown": (closes[t] / hi_252 - 1) * 100,  # how deep below the 1yr high the base sits
        "pos_52w": (closes[t] - lo_252) / (hi_252 - lo_252) * 100 if hi_252 > lo_252 else 50.0,
        "run": run,
    }


def _trough(bars: list[DailyBar]) -> int | None:
    """Launch trough = lowest close within bars[-SEARCH_LO:-SEARCH_HI]."""
    if len(bars) < SEARCH_LO + 5:
        return None
    lo, hi = len(bars) - SEARCH_LO, len(bars) - SEARCH_HI
    seg = range(lo, hi)
    return min(seg, key=lambda i: bars[i].close)


def _summary(rows: list[dict], keys: list[str]) -> dict[str, float]:
    return {k: round(st.median(r[k] for r in rows), 2) for k in keys}


async def _run() -> None:
    by_code = await _load()
    keys = ["vol_surge", "vol_vs_long", "up_vol_share", "compression", "drawdown", "pos_52w"]
    big, quiet = [], []
    for bars in by_code.values():
        if len(bars) < SEARCH_LO + 5:
            continue
        if st.mean(b.volume for b in bars[-20:]) < MIN_AVG_VOL:
            continue
        t = _trough(bars)
        if t is None:
            continue
        f = _features(bars, t)
        if f is None:
            continue
        if f["run"] >= BIG_RUN:
            big.append(f)
        elif f["run"] < QUIET_RUN:
            quiet.append(f)

    print(
        f"Launch troughs studied · BIG runners (>= {BIG_RUN:.0f}% in {FWD}d): {len(big)} "
        f"· QUIET (< {QUIET_RUN:.0f}%): {len(quiet)}"
    )
    bm, qm = _summary(big, keys), _summary(quiet, keys)
    labels = {
        "vol_surge": "vol surge (20d/prior40d)",
        "vol_vs_long": "vol vs 90d baseline",
        "up_vol_share": "up-day volume share",
        "compression": "daily-return stdev % (coil)",
        "drawdown": "% below 1yr high (base depth)",
        "pos_52w": "position in 52w range %",
    }
    print(f"\n{'PRE-LAUNCH FEATURE':<32}{'BIG runners':>13}{'QUIET':>10}{'edge':>9}")
    print("-" * 64)
    for k in keys:
        edge = bm[k] - qm[k]
        print(f"{labels[k]:<32}{bm[k]:>13}{qm[k]:>10}{edge:>+9.2f}")
    print(
        f"\nMedian forward run — BIG {round(st.median(r['run'] for r in big), 1)}% "
        f"vs QUIET {round(st.median(r['run'] for r in quiet), 1)}%"
    )
    print("\nRead the 'edge' column: features where BIG and QUIET differ most are the early tells.")


if __name__ == "__main__":
    asyncio.run(_run())
