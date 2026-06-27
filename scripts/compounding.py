"""Compounding for Scheme-3 — it already compounds; this shows how hard we can push it.

The portfolio already reinvests (each position = a slice of CURRENT equity, which grows). Two things
control how fast it compounds: (1) concentration — fewer positions = bigger bets = faster growth but
deeper drawdowns; (2) staying fully invested. This sweeps position count and projects the historical
CAGR forward (with a loud caveat that no edge compounds uninterrupted).

    uv run python scripts/compounding.py
"""

from __future__ import annotations

import asyncio

from portfolio_backtest import _load, simulate
from scheme2_value import _load_fundamentals
from scheme_lab import quality_reversal

EXITS = dict(stop=-0.10, target=0.25, hold=63)


async def _run():
    by_code, dsex = await _load()
    fin, div = await _load_fundamentals("DSE")
    sigs = quality_reversal(by_code, fin, div)

    def fn(b):
        return sigs.get(b[0].code, set())

    print("Scheme-3 — concentration (how many positions you spread across)\n")
    print(f"{'positions':>10}{'total%':>9}{'CAGR%':>8}{'maxDD%':>9}{'1,000 ->':>10}")
    print("-" * 46)
    base_cagr = None
    for mp in (4, 6, 8, 10, 12, 16):
        m = simulate(by_code, dsex, signal_fn=fn, max_pos=mp, **EXITS)
        if mp == 10:
            base_cagr = m["cagr"]
        tag = "  <- current" if mp == 10 else ""
        print(
            f"{mp:>10}{m['total']:>+9.1f}{m['cagr']:>+8.1f}{m['maxdd']:>9.1f}{m['final']:>10,.0f}{tag}"
        )

    print("\nThe magic of compounding — 1,000 growing at a steady CAGR (IF the edge held):")
    print(f"{'CAGR':>16}{'1yr':>10}{'3yr':>10}{'5yr':>10}{'10yr':>10}")
    print("-" * 56)
    for label, cagr in (
        (f"historical {base_cagr:.0f}%", base_cagr / 100),
        ("if half that 16%", 0.16),
        ("steady 25%", 0.25),
    ):
        vals = "".join(f"{1000 * (1 + cagr) ** y:>10,.0f}" for y in (1, 3, 5, 10))
        print(f"{label:>16}{vals}")
    print("\nReality check: NO edge compounds uninterrupted. A crash year, capacity limits (DSE")
    print("liquidity), and regime change all cap this. Treat 15-20% CAGR as the realistic hope,")
    print("not 32% — and even 15% doubles your money in ~5 years. That is the whole game.")


if __name__ == "__main__":
    asyncio.run(_run())
