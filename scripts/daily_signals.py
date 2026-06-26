"""Daily signal feed — today's Deep-Value Reversal entries, with levels.

The live, actionable end of the research: scans the latest EOD data for names that just FIRED the
signal (in the launch zone — deep below the 1yr high and near the 52w low — AND broke their 5-day
high), and prints each with entry / stop / target. Also lists names sitting in the zone but not yet
triggered (the watchlist for the next few sessions).

    uv run python scripts/daily_signals.py            # signals in the last 5 sessions + watchlist
    uv run python scripts/daily_signals.py --days 1   # only today's fires

Strategy basis: scripts/portfolio_backtest.py + robustness.py (this regime: ~59% win, +16% mean,
beat the index ~4x — but a single recovering-market window; not a guarantee). Stop is mandatory.
"""

from __future__ import annotations

import argparse
import asyncio

from portfolio_backtest import DEEP, MIN_AVG_VOL, NEAR_LOW, STOP, TARGET, WARMUP, _load

LOOKBACK_52W = 252


def _scan(bars, lookback_days):
    """Return ('fired', date, metrics) if a zone+trigger fired within lookback_days, else zone info."""
    n = len(bars)
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    fired_on = None
    for j in range(n - lookback_days, n):  # check the recent window for a fire
        if j < WARMUP:
            continue
        win_hi = max(highs[max(0, j - LOOKBACK_52W + 1) : j + 1])
        win_lo = min(b.low for b in bars[max(0, j - LOOKBACK_52W + 1) : j + 1])
        if win_hi <= win_lo or not closes[j]:
            continue
        below = (closes[j] / win_hi - 1) * 100
        pos = (closes[j] - win_lo) / (win_hi - win_lo) * 100
        if below < DEEP and pos < NEAR_LOW and closes[j] > max(highs[j - 5 : j]):
            fired_on = bars[j].date
    # current-day zone status
    hi = max(highs[-LOOKBACK_52W:])
    lo = min(b.low for b in bars[-LOOKBACK_52W:])
    below_now = (closes[-1] / hi - 1) * 100 if hi else 0
    pos_now = (closes[-1] - lo) / (hi - lo) * 100 if hi > lo else 50
    return fired_on, below_now, pos_now


async def _run(days):
    by_code, _ = await _load()
    latest = max(b.date for bars in by_code.values() for b in bars)
    fired, watch = [], []
    for code, bars in by_code.items():
        if len(bars) < WARMUP + 5 or sum(b.volume for b in bars[-20:]) / 20 < MIN_AVG_VOL:
            continue
        if (latest - bars[-1].date).days > 10:  # stale/delisted — hasn't traded recently
            continue
        fired_on, below, pos = _scan(bars, days)
        px = bars[-1].close
        row = (code, fired_on, px, below, pos)
        if fired_on is not None:
            fired.append(row)
        elif below < DEEP and pos < NEAR_LOW:
            watch.append(row)

    print(f"As of EOD {latest}  ·  EOD/delayed data  ·  stop is mandatory\n")
    print(f"=== FIRED (zone + broke 5d high) in last {days} session(s): {len(fired)} ===")
    if fired:
        print(
            f"  {'CODE':<12}{'fired':>12}{'entry':>9}{'stop':>9}{'target':>9}  {'below_hi':>8}{'off_low':>8}"
        )
        for code, fon, px, below, pos in sorted(fired, key=lambda r: r[1] or latest, reverse=True):
            print(
                f"  {code:<12}{fon!s:>12}{px:>9.1f}{px * (1 + STOP):>9.1f}{px * (1 + TARGET):>9.1f}"
                f"  {below:>7.0f}%{pos:>7.0f}%"
            )
    else:
        print("  (none — the signal is selective; check the watchlist)")

    print(f"\n=== WATCHLIST (in launch zone, no trigger yet): {len(watch)} ===")
    print(f"  {'CODE':<12}{'price':>9}{'below_hi':>10}{'off_low':>9}")
    for code, _fon, px, below, pos in sorted(watch, key=lambda r: r[4])[:15]:
        print(f"  {code:<12}{px:>9.1f}{below:>9.0f}%{pos:>8.0f}%")
    print(
        "\nLevels: entry = last close, stop = -10%, target = +25% (~2.5:1). Size so one stop-out is "
        "a small % of capital; diversify (the backtest used 10 positions)."
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=5, help="look-back window for a fired signal")
    asyncio.run(_run(ap.parse_args().days))


if __name__ == "__main__":
    main()
