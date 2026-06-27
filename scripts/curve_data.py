"""Emit monthly-sampled wealth curves for 200,000 BDT under three plans — for the chart.

All three start from the SAME 200,000 so they're directly comparable:
  A) concentrated  — 10% of equity per name, max 10 (the validated +74% method)
  B) fixed 10k     — 10,000 per trade, grab every signal you can afford (waitlist when cash runs out)
  C) fixed 10k + compound — same, but the stake scales up as wealth grows
Prints JSON the chart reads.
"""

from __future__ import annotations

import asyncio
import json

from portfolio_backtest import COST, _load, simulate
from scheme2_value import _load_fundamentals
from scheme_lab import quality_reversal

STOP, TARGET, HOLD = -0.10, 0.25, 63
START = 200_000.0
UNIT = 10_000.0


def _fixed_curve(by_code, sigs, axis, bar_map, compound):
    cash, positions, curve = START, {}, []
    last_px = {}
    for d in axis:
        for code in list(positions):
            p = positions[code]
            bar = bar_map[code].get(d)
            if not bar:
                continue
            last_px[code] = bar.close
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
                cash += p["shares"] * exit_px * (1 - COST)
                del positions[code]
        wealth = cash + sum(
            positions[c]["shares"] * last_px.get(c, positions[c]["entry"]) for c in positions
        )
        stake = UNIT * (wealth / START) if compound else UNIT
        for code in sigs:
            if d in sigs[code] and code not in positions:
                bar = bar_map[code].get(d)
                if bar and bar.close and cash >= stake * (1 + COST):
                    positions[code] = {"entry": bar.close, "held": 0, "shares": stake / bar.close}
                    cash -= stake * (1 + COST)
                    last_px[code] = bar.close
        wealth = cash + sum(
            positions[c]["shares"] * last_px.get(c, positions[c]["entry"]) for c in positions
        )
        curve.append((d, wealth))
    return curve


async def _run():
    by_code, dsex = await _load()
    fin, div = await _load_fundamentals("DSE")
    sigs = quality_reversal(by_code, fin, div)
    bar_map = {c: {b.date: b for b in bars} for c, bars in by_code.items()}
    axis = sorted({b.date for bars in by_code.values() for b in bars})

    m = simulate(
        by_code,
        dsex,
        signal_fn=lambda b: sigs.get(b[0].code, set()),
        stop=STOP,
        target=TARGET,
        hold=HOLD,
        max_pos=10,
    )
    conc = [(d, e / 1000.0 * START) for d, e in m["curve"]]  # scale notional 1,000 -> 200,000
    fixed = _fixed_curve(by_code, sigs, axis, bar_map, compound=False)
    comp = _fixed_curve(by_code, sigs, axis, bar_map, compound=True)

    def sample(curve):  # ~monthly points keep the chart clean
        return [
            (d.isoformat(), round(v))
            for i, (d, v) in enumerate(curve)
            if i % 21 == 0 or i == len(curve) - 1
        ]

    out = {
        "concentrated": sample(conc),
        "fixed": sample(fixed),
        "compound": sample(comp),
        "ends": {
            "concentrated": round(conc[-1][1]),
            "fixed": round(fixed[-1][1]),
            "compound": round(comp[-1][1]),
        },
    }
    print(json.dumps(out))


if __name__ == "__main__":
    asyncio.run(_run())
