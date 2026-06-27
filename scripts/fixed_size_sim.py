"""'Buy 10k each, take everything, compound the profit' — what does THAT look like?

The flagship backtest sized every position at 10% of current equity and capped at 10 names. This
models the user's alternative: a fixed base stake per trade, NO position cap (grab every signal),
and profits rolled forward so the stake grows. It answers two honest questions:
  1. How much capital does "always have money to grab everything" actually need? (= the peak amount
     deployed at once — when the most positions are open simultaneously)
  2. Fixed stake vs compounding the stake — how different is the outcome?

Same Scheme-3 signals + exits (-10% / +25% / 63d) + 0.8% round-trip cost as everywhere else.

    uv run python scripts/fixed_size_sim.py
"""

from __future__ import annotations

import asyncio

from portfolio_backtest import COST, _load
from scheme2_value import _load_fundamentals
from scheme_lab import quality_reversal

STOP, TARGET, HOLD = -0.10, 0.25, 63
UNIT = 10_000  # base stake per trade
CAPITAL = 200_000  # your reference pot, for context


async def _run():
    by_code, _dsex = await _load()
    fin, div = await _load_fundamentals("DSE")
    sigs = quality_reversal(by_code, fin, div)
    bar_map = {c: {b.date: b for b in bars} for c, bars in by_code.items()}
    last_bar = {c: bars[-1] for c, bars in by_code.items()}
    axis = sorted({b.date for bars in by_code.values() for b in bars})

    print(
        f"Base stake {UNIT:,.0f}/trade · take EVERY Scheme-3 signal (no 10-name cap) · cost {COST * 2:.1%} round trip\n"
    )
    print(
        f"{'mode':<14}{'trades':>8}{'win%':>7}{'peak open':>11}{'capital needed':>16}{'profit':>13}{'final wealth':>15}"
    )
    print("-" * 84)

    for mode in ("fixed 10k", "compound"):
        positions, realized, trades = {}, 0.0, []
        peak_open, peak_deploy = 0, 0.0
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
                    realized += p["unit"] * (1 + ret) * (1 - COST) - p["unit"] * (1 + COST)
                    trades.append(ret)
                    del positions[code]
            # stake grows with banked profit when compounding; flat otherwise
            mult = (CAPITAL + realized) / CAPITAL if mode == "compound" else 1.0
            unit = UNIT * mult
            for code in sigs:
                if d in sigs[code] and code not in positions:
                    bar = bar_map[code].get(d)
                    if bar and bar.close:
                        positions[code] = {"entry": bar.close, "held": 0, "unit": unit}
            peak_open = max(peak_open, len(positions))
            peak_deploy = max(peak_deploy, sum(p["unit"] for p in positions.values()))

        # mark any still-open positions to their last known price, so wealth is complete
        for code, p in positions.items():
            ret = last_bar[code].close / p["entry"] - 1
            realized += p["unit"] * (1 + ret) * (1 - COST) - p["unit"] * (1 + COST)
            trades.append(ret)
        win = sum(1 for t in trades if t > 0) / len(trades) * 100
        print(
            f"{mode:<14}{len(trades):>8}{win:>6.0f}%{peak_open:>11}{peak_deploy:>16,.0f}"
            f"{realized:>+13,.0f}{CAPITAL + realized:>15,.0f}"
        )

    print("\n  'Capital needed' = the most stake deployed at once (peak open positions x stake).")
    print(
        f"  With only {CAPITAL:,.0f} you can grab everything ONLY while that stays under {CAPITAL:,.0f};"
    )
    print("  beyond it you'd be back to a waitlist. Profit shown after the 0.8% round-trip cost.")


if __name__ == "__main__":
    asyncio.run(_run())
