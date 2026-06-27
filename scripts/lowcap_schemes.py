"""Low-cap scheme hunt — find an entry edge inside the small-cap universe only.

Small caps behave differently (more momentum/pump, bigger value mispricing, more manipulation), so
rules that failed market-wide might work here — and vice versa. Restricts to the bottom slice by
market cap (still above the liquidity floor), tests several entry rules on the same engine, ranks
them, and out-of-sample checks the winner.

    uv run python scripts/lowcap_schemes.py

LOUD caveat: small-cap EOD-close fills are the LEAST realistic — wide spreads, thin books, and
pump-and-dump manipulation mean live results will trail the backtest more here than anywhere else.
Treat any winner as a lead to forward-test with small size, not a proven money machine.
"""

from __future__ import annotations

import asyncio
import datetime as dt

from portfolio_backtest import MIN_AVG_VOL, WARMUP, _load, simulate
from scheme2_value import _load_fundamentals
from scheme_lab import quality_reversal
from schemes import _prep, deep_value_reversal, near_low_reclaim, oversold_bounce, volume_breakout
from sqlalchemy import select

from bulls.core.db import get_sessionmaker
from bulls.core.models import CompanyProfile

CAP_PCTILE = 0.40  # "low cap" = below this percentile of liquid-universe market cap
EXITS = dict(stop=-0.12, target=0.30, hold=63, max_pos=10)
SPLIT = dt.date(2025, 9, 1)


async def _lowcap_universe(market):
    sm = get_sessionmaker()
    async with sm() as session:
        profs = list(
            await session.scalars(select(CompanyProfile).where(CompanyProfile.market == market))
        )
    caps = {p.code: p.market_cap_mn for p in profs if p.market_cap_mn}
    ordered = sorted(caps.values())
    thresh = ordered[int(len(ordered) * CAP_PCTILE)]
    return {c for c, v in caps.items() if v < thresh}, thresh


# --- low-cap-tailored entry rules (price/volume) ---
def vol_surge_off_low(bars):
    """Near 52w low + a >2x volume spike on an up day — early accumulation/pump ignition."""
    c, _h, _r, _s20, _s200, v20, hi, lo = _prep(bars)
    v = [float(b.volume) for b in bars]
    out = set()
    for i in range(WARMUP, len(bars)):
        if not hi[i] or hi[i] <= lo[i] or not v20[i]:
            continue
        pos = (c[i] - lo[i]) / (hi[i] - lo[i]) * 100
        if pos < 25 and v[i] > 2 * v20[i] and c[i] > c[i - 1]:
            out.add(bars[i].date)
    return out


def _per_code(rule, bars_by_code, lowcap):
    return {c: rule(b) for c, b in bars_by_code.items() if c in lowcap}


async def _run():
    by_code, dsex = await _load()
    fin, div = await _load_fundamentals("DSE")
    lowcap, thresh = await _lowcap_universe("DSE")
    liquid_low = {
        c: b
        for c, b in by_code.items()
        if c in lowcap and sum(x.volume for x in b[-20:]) / 20 >= MIN_AVG_VOL
    }
    print(f"Low-cap universe: market cap < {thresh:,.0f} mn · {len(liquid_low)} liquid names\n")

    qr = quality_reversal(by_code, fin, div)  # {code:set}
    schemes = {
        "deep-value reversal": _per_code(deep_value_reversal, liquid_low, lowcap),
        "quality reversal": {c: qr.get(c, set()) for c in liquid_low},
        "vol-surge off low": _per_code(vol_surge_off_low, liquid_low, lowcap),
        "volume breakout": _per_code(volume_breakout, liquid_low, lowcap),
        "near-low reclaim": _per_code(near_low_reclaim, liquid_low, lowcap),
        "oversold bounce": _per_code(oversold_bounce, liquid_low, lowcap),
    }

    print(
        f"{'LOW-CAP SCHEME':<24}{'total%':>9}{'maxDD%':>9}{'trades':>8}{'win%':>7}{'avg W/L':>11}"
    )
    print("-" * 68)
    results = {}
    for name, sigs in schemes.items():
        m = simulate(by_code, dsex, signal_fn=lambda b, s=sigs: s.get(b[0].code, set()), **EXITS)
        results[name] = (m, sigs)
    ranked = sorted(results.items(), key=lambda r: r[1][0]["total"], reverse=True)
    for name, (m, _s) in ranked:
        print(
            f"{name:<24}{m['total']:>+9.1f}{m['maxdd']:>9.1f}{m['n_trades']:>8}{m['winrate']:>6.0f}%"
            f"{'+' + str(round(m['avg_win'])) + '/' + str(round(m['avg_loss'])):>11}"
        )

    # out-of-sample check on the winner
    best_name, (_m, best_sigs) = ranked[0]
    print(f"\nOut-of-sample check — winner: {best_name} (split {SPLIT})")
    for label, lo, hi in (
        ("TRAIN", dt.date(2000, 1, 1), SPLIT),
        ("TEST ", SPLIT, dt.date(2100, 1, 1)),
    ):
        half = {c: {d for d in ds if lo <= d < hi} for c, ds in best_sigs.items()}
        mm = simulate(by_code, dsex, signal_fn=lambda b, s=half: s.get(b[0].code, set()), **EXITS)
        ix = [v for d, v in sorted(dsex.items()) if lo <= d < hi]
        idx = (ix[-1] / ix[0] - 1) * 100 if len(ix) > 1 else 0
        print(
            f"  {label}  {mm['total']:>+7.1f}%   vs index {idx:>+5.1f}%   trades {mm['n_trades']:>3}   win {mm['winrate']:.0f}%"
        )


if __name__ == "__main__":
    asyncio.run(_run())
