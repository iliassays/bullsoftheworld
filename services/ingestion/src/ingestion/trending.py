"""Compute the daily 'Watch today' ranking — the trending engine.

Phase-0 backtest finding (2y of daily_bars, walk-forward): the only signals with real out-of-sample
edge are the **self-normalized volume and turnover surge** — each stock measured against its OWN
recent normal. So the rank is just `vol_z + turnover_z` (log-space z vs the trailing 60 days,
excluding today). Move/breakout/52-week proximity carry little edge, so they DON'T drive the rank —
they're attached only as descriptive `reasons` chips for context.

Regulatory posture (descriptive, not advice; don't be a pump megaphone): the PUBLIC universe is gated
hard — liquid names only (turnover + market-cap floors), Z-category excluded — so our audience can't
move what we surface. The score is direction-agnostic (a volume surge counts whether price rose or
fell), so the list is balanced up/down, not a one-sided "what's going up" hype board.

    uv run python -m ingestion.trending DSE
"""

from __future__ import annotations

import asyncio
import datetime as dt
import sys
from typing import Any

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.db import get_sessionmaker
from bulls.core.models import CompanyProfile, DailyBar, Symbol, TrendingScore

BASELINE_W = 60         # trailing window for the self-normal baseline
MIN_BARS = 60           # need at least this much history to score
TURNOVER_FLOOR_TK = 5_000_000   # median 20-day turnover floor (~৳50 lakh/day) — tradeable only
MCAP_FLOOR_MN = 500             # ~৳50 crore market cap floor
TOP_N = 25              # how many to persist (strip shows ~8, list ~15)


def _z(series: np.ndarray, today: float) -> float | None:
    """z-score of `today` vs the trailing baseline (which excludes today). None if degenerate."""
    if len(series) < BASELINE_W // 2:
        return None
    mean, std = float(np.mean(series)), float(np.std(series))
    if std <= 1e-9:
        return None
    return (today - mean) / std


def _reasons(*, vol_mult, turnover_cr, turnover_mult, pct_from_high, pct_from_low, change_pct) -> list[dict[str, Any]]:
    """Descriptive context chips, most-important first, capped at 3. Display only — not rank drivers."""
    chips: list[dict[str, Any]] = []
    if change_pct >= 9.5:
        chips.append({"kind": "limit_up"})
    elif change_pct <= -9.5:
        chips.append({"kind": "limit_down"})
    if vol_mult and vol_mult >= 2:
        chips.append({"kind": "volume", "mult": round(vol_mult, 1)})
    if turnover_cr and turnover_cr >= 1:
        chip = {"kind": "turnover", "cr": round(turnover_cr)}
        if turnover_mult and turnover_mult >= 2:
            chip["mult"] = round(turnover_mult, 1)
        chips.append(chip)
    if pct_from_high is not None and pct_from_high >= -3:
        chips.append({"kind": "near_high"})
    elif pct_from_low is not None and pct_from_low <= 3:
        chips.append({"kind": "near_low"})
    if abs(change_pct) >= 5 and not any(c["kind"] in ("limit_up", "limit_down") for c in chips):
        chips.append({"kind": "move", "pct": round(change_pct, 1)})
    return chips[:3]


async def compute_trending(market: str) -> dict[str, int]:
    sm = get_sessionmaker()
    async with sm() as session:
        syms = {
            s.code: s
            for s in await session.scalars(
                select(Symbol).where(
                    Symbol.market == market, Symbol.is_active.is_(True), Symbol.is_hidden.is_(False)
                )
            )
        }
        mcap = {
            p.code: p.market_cap_mn
            for p in await session.scalars(
                select(CompanyProfile).where(CompanyProfile.market == market)
            )
        }

    scored: list[dict[str, Any]] = []
    as_of: dt.date | None = None
    async with sm() as session:
        for code, sym in syms.items():
            if sym.category == "Z":  # exclude the speculative/non-performing board
                continue
            cap = mcap.get(code)
            if cap is not None and cap < MCAP_FLOOR_MN:
                continue
            bars = list(
                await session.scalars(
                    select(DailyBar)
                    .where(DailyBar.market == market, DailyBar.code == code)
                    .order_by(DailyBar.date.desc())
                    .limit(BASELINE_W + 5)
                )
            )
            if len(bars) < MIN_BARS:
                continue
            bars = list(reversed(bars))  # ascending; last = today
            t = bars[-1]
            closes = np.array([b.close for b in bars], dtype=float)
            vols = np.array([b.volume for b in bars], dtype=float)
            turns = closes * vols
            if t.close <= 0 or t.volume <= 0:
                continue

            baseline = slice(-BASELINE_W - 1, -1)  # trailing window, excludes today
            vol_z = _z(np.log1p(vols[baseline]), float(np.log1p(t.volume)))
            to_z = _z(np.log1p(turns[baseline]), float(np.log1p(turns[-1])))
            if vol_z is None or to_z is None:
                continue

            med20_turnover = float(np.median(turns[-20:]))
            if med20_turnover < TURNOVER_FLOOR_TK:  # liquidity gate — can't surface what we'd move
                continue

            prev_close = bars[-2].close
            change_pct = (t.close / prev_close - 1) * 100 if prev_close else 0.0
            vol_mult = t.volume / np.mean(vols[-21:-1]) if np.mean(vols[-21:-1]) > 0 else None
            to_mult = turns[-1] / np.mean(turns[-21:-1]) if np.mean(turns[-21:-1]) > 0 else None
            hi = float(np.max(closes[-252:]))
            lo = float(np.min(closes[-252:]))
            pct_from_high = (t.close / hi - 1) * 100 if hi else None
            pct_from_low = (t.close / lo - 1) * 100 if lo else None

            score = vol_z + to_z
            scored.append(
                {
                    "market": market,
                    "code": code,
                    "as_of_date": t.date,
                    "score": round(score, 4),
                    "change_pct": round(change_pct, 2),
                    "direction": "up" if change_pct > 0.1 else "down" if change_pct < -0.1 else "flat",
                    "heating_up": bool(vol_z >= 2 and to_z >= 2),
                    "reasons": _reasons(
                        vol_mult=vol_mult,
                        turnover_cr=turns[-1] / 1e7,
                        turnover_mult=to_mult,
                        pct_from_high=pct_from_high,
                        pct_from_low=pct_from_low,
                        change_pct=change_pct,
                    ),
                }
            )
            as_of = t.date

    scored.sort(key=lambda r: r["score"], reverse=True)
    top = scored[:TOP_N]
    for i, r in enumerate(top, start=1):
        r["rank"] = i

    async with sm() as session:
        await session.execute(delete(TrendingScore).where(TrendingScore.market == market))
        if top:
            await session.execute(pg_insert(TrendingScore).values(top))
        await session.commit()

    return {"eligible": len(scored), "stored": len(top), "as_of": as_of.isoformat() if as_of else "—"}


async def _run(market: str) -> None:
    stats = await compute_trending(market)
    print(f"[trending] {stats}")


def main() -> None:
    market = sys.argv[1] if len(sys.argv) > 1 else "DSE"
    asyncio.run(_run(market))


if __name__ == "__main__":
    main()
