"""Big-mover study — after a big single-day surge (or plunge) on volume, what happens next?

DSE has lots of explosive single-day moves (often near the circuit limit, on a volume spike). We've
tested slow momentum (loses) and washout reversals (wins). This tests the OTHER thing: the day a stock
jumps hard. Does it CONTINUE (momentum / news / pump ignition) or REVERSE (exhaustion)? Measures
forward 5/10/20-day returns after big up-days and big down-days, vs the all-day baseline.

    uv run python scripts/bigmover_study.py
"""

from __future__ import annotations

import asyncio
import statistics as st

from portfolio_backtest import _load

BIG = 0.09  # a "big" day = +/-9% (near a typical DSE daily limit)
VOL_X = 2.0  # on >= 2x the 20-day average volume
FWDS = (5, 10, 20)
MIN_AVG_VOL = 5_000


def _summary(label, samples):
    if not samples:
        print(f"  {label:<22} (no events)")
        return
    cells = []
    for fw in FWDS:
        xs = [s[fw] for s in samples if s[fw] is not None]
        med = st.median(xs)
        hit = sum(1 for x in xs if x > 0) / len(xs) * 100
        cells.append(f"{med:>+6.1f}% ({hit:>2.0f}%)")
    print(f"  {label:<22}{'   '.join(cells)}   n={len(samples)}")


async def _run():
    by_code, _ = await _load()
    big_up, big_dn, baseline = [], [], []
    for bars in by_code.values():
        if len(bars) < 60 or sum(b.volume for b in bars[-20:]) / 20 < MIN_AVG_VOL:
            continue
        closes = [b.close for b in bars]
        vols = [b.volume for b in bars]
        for i in range(20, len(bars) - max(FWDS)):
            if not closes[i - 1]:
                continue
            ret = closes[i] / closes[i - 1] - 1
            avg20 = sum(vols[i - 20 : i]) / 20 or 1
            fwd = {fw: (closes[i + fw] / closes[i] - 1) * 100 if closes[i] else None for fw in FWDS}
            baseline.append(fwd)
            if vols[i] >= VOL_X * avg20:
                if ret >= BIG:
                    big_up.append(fwd)
                elif ret <= -BIG:
                    big_dn.append(fwd)

    print(
        f"Forward return after the event — median (% positive). Threshold: +/-{BIG:.0%} on {VOL_X:.0f}x volume.\n"
    )
    print(f"  {'EVENT':<22}{'+5d':<13}{'+10d':<13}{'+20d':<13}")
    print("  " + "-" * 60)
    _summary("big UP day", big_up)
    _summary("big DOWN day", big_dn)
    _summary("any day (baseline)", baseline)
    print("\nRead: if big-UP medians/hit-rates beat baseline -> surges CONTINUE (a momentum edge).")
    print("If big-DOWN beats baseline -> plunges bounce (reversal). Compare to baseline, not zero.")


if __name__ == "__main__":
    asyncio.run(_run())
