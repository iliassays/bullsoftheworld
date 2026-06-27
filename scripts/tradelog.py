"""Trade log — the backtest as a plain list of trades you can read.

"On <date> bought CODE at X, on <date> sold at Y, made Z%." Runs the Deep-Value Reversal sim and
prints every trade in date order with the exit reason, then the running tally. This is the human view
of scripts/portfolio_backtest.py — same engine, readable output.

    uv run python scripts/tradelog.py            # all trades
    uv run python scripts/tradelog.py --last 25  # most recent 25
"""

from __future__ import annotations

import argparse
import asyncio

from portfolio_backtest import _load, simulate


async def _run(last: int | None):
    by_code, dsex = await _load()
    m = simulate(by_code, dsex)
    log = sorted(m["trade_log"], key=lambda t: t["in_date"])
    shown = log[-last:] if last else log

    print(f"Deep-Value Reversal — {len(log)} trades over the backtest. Showing {len(shown)}.\n")
    print(f"  {'BOUGHT':>11} {'CODE':<11}{'in':>8}  {'SOLD':>11}{'out':>8}{'ret%':>8}{'days':>6}  why")
    for t in shown:
        print(f"  {t['in_date']!s:>11} {t['code']:<11}{t['in_px']:>8.2f}  "
              f"{t['out_date']!s:>11}{t['out_px']:>8.2f}{t['ret']:>+8.1f}{t['held']:>6}  {t['reason']}")

    wins = [t for t in log if t["ret"] > 0]
    print(f"\n  Tally: {len(log)} trades · {len(wins)} winners ({len(wins) / len(log) * 100:.0f}%) · "
          f"avg winner +{sum(t['ret'] for t in wins) / len(wins):.1f}% · "
          f"avg loser {sum(t['ret'] for t in log if t['ret'] <= 0) / max(1, len(log) - len(wins)):.1f}%")
    print(f"  Portfolio: 1,000 -> {m['final']:,.0f} ({m['total']:+.1f}%) over the period, "
          f"worst dip {m['maxdd']:.0f}% along the way.")
    print("\n  (Equal-weight, max 10 at once, 0.4%/side cost. EOD/delayed data, single market regime.)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--last", type=int, default=None, help="show only the most recent N trades")
    asyncio.run(_run(ap.parse_args().last))


if __name__ == "__main__":
    main()
