"""Signal backtest — does a 'washed-out name + turn trigger' actually pay, out of sample?

Walks the FULL bar history day by day (point-in-time, no lookahead). At each date, for each liquid
name, checks the launch ZONE (deep below 1yr high + near 52w low) and whether a TURN TRIGGER fires,
then measures the forward 3-month (~63 trading-day) return. Reports each trigger's hit-rate, mean/
median return, run-to-peak (MFE) and worst-dip (MAE) vs the market baseline, plus an EARLY-vs-LATE
split — the honest out-of-sample check that matters before anyone pays for a signal.

    uv run python scripts/signal_backtest.py

Honesty: 2-year single-regime window (post-floor-price DSE recovery — favors mean-reversion).
A positive, *stable* edge here is promising but not proof across regimes. EOD data; costs/slippage
not modelled. This validates direction + rough magnitude, not a guaranteed return.
"""

from __future__ import annotations

import asyncio
import statistics as st
from collections import defaultdict

from sqlalchemy import select

from bulls.core.db import get_sessionmaker
from bulls.core.models import DailyBar, MarketSummary

MARKET = "DSE"
FWD = 63  # ~3 months in trading days
WARMUP = 60
MIN_AVG_VOL = 5_000
COOLDOWN = 20  # don't re-fire the same name within N days (keep signals as discrete events)
DEEP = -40.0  # % below 1yr high to count as washed-out
NEAR_LOW = 15.0  # within this % of the 52w low


def _sma(vals, n):
    out = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def _rsi(closes, n=14):
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        ch = closes[i] - closes[i - 1]
        gains += max(ch, 0)
        losses += max(-ch, 0)
    ag, al = gains / n, losses / n
    out[n] = 100 - 100 / (1 + ag / al) if al else 100.0
    for i in range(n + 1, len(closes)):
        ch = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(ch, 0)) / n
        al = (al * (n - 1) + max(-ch, 0)) / n
        out[i] = 100 - 100 / (1 + ag / al) if al else 100.0
    return out


def _roll(vals, n, fn):
    out = [None] * len(vals)
    for i in range(len(vals)):
        out[i] = fn(vals[max(0, i - n + 1) : i + 1])
    return out


async def _load():
    sm = get_sessionmaker()
    async with sm() as session:
        bars = list(
            await session.scalars(
                select(DailyBar).where(DailyBar.market == MARKET).order_by(DailyBar.code, DailyBar.date)
            )
        )
        dsex = dict(
            (r.date, r.dsex)
            for r in await session.scalars(select(MarketSummary).where(MarketSummary.market == MARKET))
        )
    by_code = defaultdict(list)
    for b in bars:
        by_code[b.code].append(b)
    return by_code, dsex


def _triggers(closes, highs, rsi, sma10, i):
    """Return which turn-triggers fire at index i (each needs i-1 context)."""
    return {
        "zone_only": True,  # baseline: in the zone, no trigger
        "rsi_x35": rsi[i - 1] is not None and rsi[i] is not None and rsi[i - 1] <= 35 < rsi[i],
        "rsi_x40": rsi[i - 1] is not None and rsi[i] is not None and rsi[i - 1] <= 40 < rsi[i],
        "cross_sma10": sma10[i] is not None and closes[i] > sma10[i] and closes[i - 1] <= sma10[i - 1],
        "two_up_days": closes[i] > closes[i - 1] > closes[i - 2],
        "break_5d_high": closes[i] > max(highs[i - 5 : i]),
    }


async def _run():
    by_code, dsex = await _load()
    variants = ["zone_only", "rsi_x35", "rsi_x40", "cross_sma10", "two_up_days", "break_5d_high"]
    # records[variant] = list of (entry_date, fwd_return, mfe, mae)
    records = {v: [] for v in variants}
    universe_fwd = []  # baseline: every liquid stock-date's forward return

    for bars in by_code.values():
        if len(bars) < WARMUP + FWD + 5 or st.mean(b.volume for b in bars[-20:]) < MIN_AVG_VOL:
            continue
        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        rsi = _rsi(closes)
        sma10 = _sma(closes, 10)
        hi252 = _roll(highs, 252, max)
        lo252 = _roll([b.low for b in bars], 252, min)
        last_fire = {v: -999 for v in variants}

        for i in range(WARMUP, len(bars) - FWD):
            if not closes[i] or not hi252[i] or hi252[i] <= lo252[i]:
                continue
            fwd = (closes[i + FWD] / closes[i] - 1) * 100
            window = bars[i + 1 : i + 1 + FWD]
            mfe = (max(b.high for b in window) / closes[i] - 1) * 100
            mae = (min(b.low for b in window) / closes[i] - 1) * 100
            universe_fwd.append(fwd)

            below_high = (closes[i] / hi252[i] - 1) * 100
            pos_low = (closes[i] - lo252[i]) / (hi252[i] - lo252[i]) * 100
            if below_high >= DEEP or pos_low >= NEAR_LOW:  # not in the launch zone
                continue
            fired = _triggers(closes, highs, rsi, sma10, i)
            for v in variants:
                if fired[v] and i - last_fire[v] >= COOLDOWN:
                    last_fire[v] = i
                    records[v].append((bars[i].date, fwd, mfe, mae))

    # market baseline: average DSEX forward 63d over the period
    dts = sorted(dsex)
    mkt = [
        (dsex[dts[k + FWD]] / dsex[dts[k]] - 1) * 100
        for k in range(len(dts) - FWD)
        if dsex[dts[k]] and dsex[dts[k + FWD]]
    ]
    mkt_mean = st.mean(mkt) if mkt else 0.0
    base_mean = st.mean(universe_fwd) if universe_fwd else 0.0
    base_hit = sum(1 for x in universe_fwd if x > 0) / len(universe_fwd) * 100

    print(f"Forward horizon {FWD}d (~3mo). Liquid stock-dates evaluated: {len(universe_fwd):,}")
    print(f"Baselines — any liquid name: mean {base_mean:+.1f}%, hit {base_hit:.0f}%  |  "
          f"DSEX index: mean {mkt_mean:+.1f}%\n")
    print(f"{'TRIGGER (in launch zone)':<26}{'n':>5}{'hit%':>6}{'mean':>8}{'median':>8}{'peak':>8}{'dip':>8}{'vs base':>9}")
    print("-" * 80)
    for v in variants:
        rs = records[v]
        if not rs:
            print(f"{v:<26}{'0':>5}")
            continue
        fwds = [r[1] for r in rs]
        m = st.mean(fwds)
        print(f"{v:<26}{len(rs):>5}{sum(1 for x in fwds if x > 0) / len(fwds) * 100:>5.0f}%"
              f"{m:>+8.1f}{st.median(fwds):>+8.1f}"
              f"{st.median(r[2] for r in rs):>+8.1f}{st.median(r[3] for r in rs):>+8.1f}"
              f"{m - base_mean:>+9.1f}")

    # out-of-sample sanity: early half vs late half of entry dates
    print("\nStability (mean fwd return, early-half vs late-half of signals):")
    for v in variants[1:]:
        rs = sorted(records[v])
        if len(rs) < 12:
            continue
        mid = len(rs) // 2
        e = st.mean(r[1] for r in rs[:mid])
        late = st.mean(r[1] for r in rs[mid:])
        print(f"  {v:<22} early {e:+6.1f}%  ({rs[0][0]}..)   late {late:+6.1f}%  (..{rs[-1][0]})")


if __name__ == "__main__":
    asyncio.run(_run())
