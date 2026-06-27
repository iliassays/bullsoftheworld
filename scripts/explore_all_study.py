"""'I have unlimited money — take EVERY signal, hold each to exit.' Does it work, and what's the catch?

The user's model: no 10-name cap, fund every signal with a fixed stake, hold each to its own exit.
If every signal is a positive-edge bet, taking more of them makes more TOTAL profit and is more
diversified — that part of the intuition is correct. This measures the real shape of it:
  - how often signals actually arrive (the '5 per day' fear vs reality)
  - how much capital you must reserve (the peak) and how much sits idle (peak vs average)
  - return on the capital you commit, vs the concentrated 200k method (+74%)

    uv run python scripts/explore_all_study.py
"""

from __future__ import annotations

import asyncio
import statistics as st

from portfolio_backtest import COST, _load
from scheme2_value import _load_fundamentals
from scheme_lab import quality_reversal

STOP, TARGET, HOLD = -0.10, 0.25, 63
STAKE = 20_000  # the user's ~100,000 / 5 names


async def _run():
    by_code, _dsex = await _load()
    fin, div = await _load_fundamentals("DSE")
    sigs = quality_reversal(by_code, fin, div)
    bar_map = {c: {b.date: b for b in bars} for c, bars in by_code.items()}
    last_bar = {c: bars[-1] for c, bars in by_code.items()}
    axis = sorted({b.date for bars in by_code.values() for b in bars})

    positions, realized, trades = {}, 0.0, []
    deploy_series, conc_series, buys_per_day = [], [], []
    for d in axis:
        for code in list(positions):
            p = positions[code]
            bar = bar_map[code].get(d)
            if not bar:
                continue
            p["held"] += 1
            stop_px, tgt_px = p["entry"] * (1 + STOP), p["entry"] * (1 + TARGET)
            exit_px = None
            if bar.low <= stop_px:
                exit_px = stop_px
            elif bar.high >= tgt_px:
                exit_px = tgt_px
            elif p["held"] >= HOLD:
                exit_px = bar.close
            if exit_px is not None:
                ret = exit_px / p["entry"] - 1
                realized += STAKE * (1 + ret) * (1 - COST) - STAKE * (1 + COST)
                trades.append(ret)
                del positions[code]
        bought = 0
        for code in sigs:
            if d in sigs[code] and code not in positions:
                bar = bar_map[code].get(d)
                if bar and bar.close:
                    positions[code] = {"entry": bar.close, "held": 0}
                    bought += 1
        buys_per_day.append(bought)
        conc_series.append(len(positions))
        deploy_series.append(len(positions) * STAKE)

    for code, p in positions.items():  # close survivors at last price
        ret = last_bar[code].close / p["entry"] - 1
        realized += STAKE * (1 + ret) * (1 - COST) - STAKE * (1 + COST)
        trades.append(ret)

    peak_cap = max(deploy_series)
    avg_cap = st.mean([x for x in deploy_series if x > 0])
    win = sum(1 for t in trades if t > 0) / len(trades) * 100
    busy = [b for b in buys_per_day if b > 0]

    print("=== How often do signals actually arrive? (the '5 every day' worry) ===")
    print(
        f"  Days with ANY new signal: {len(busy)} of {len(axis)}  ({len(busy) / len(axis) * 100:.0f}% of days)"
    )
    print(f"  On a day that fires: median {st.median(busy):.0f} new names, busiest day {max(busy)}")
    print(
        f"  Days with 5+ at once: {sum(1 for b in buys_per_day if b >= 5)}  ·  10+: {sum(1 for b in buys_per_day if b >= 10)}"
    )

    print(f"\n=== Take EVERY signal, {STAKE:,.0f} each, hold to exit, unlimited cash ===")
    print(f"  Trades over the 2 years: {len(trades)}  ·  win {win:.0f}%")
    print(f"  Positions open at once: avg {st.mean(conc_series):.0f}, peak {max(conc_series)}")
    print(f"  Capital you must reserve (peak): {peak_cap:,.0f}")
    print(
        f"  Capital actually working (avg):  {avg_cap:,.0f}   -> ~{(1 - avg_cap / peak_cap) * 100:.0f}% sits idle vs the peak"
    )
    print(f"  Total profit (after cost): {realized:+,.0f}")
    print(f"  Return on peak capital reserved: {realized / peak_cap * 100:+.0f}%")
    print(f"  Return on avg capital working:   {realized / avg_cap * 100:+.0f}%")

    print("\n=== vs the concentrated 200,000 method ===")
    print(
        "  Concentrated (10% of equity, max 10): 200,000 -> ~348,000 = +74% on 200k, profit +148,000"
    )
    print(
        "  Take-everything makes more TOTAL taka, but ties up far more capital at a lower return rate,"
    )
    print(
        "  because most of the reserved money sits idle between signal bursts and the stake never compounds."
    )


if __name__ == "__main__":
    asyncio.run(_run())
