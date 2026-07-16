"""Hedge — your daily morning list (Scheme-3 Quality Reversal, the validated flagship).

What to check each morning. Scans the latest EOD data for names that just FIRED the flagship signal —
a washed-out, profitable, cheap company turning up — and prints each with entry / stop / target / hold
and the quality context (P/E, ROE, sector). Also a WATCHLIST: names set up in the zone, waiting only
for the breakout trigger.

    uv run python scripts/hedge_daily.py            # fired in last 5 sessions + watchlist
    uv run python scripts/hedge_daily.py --days 1   # only today

Scheme-3 (backtested, out-of-sample validated): ~58% win, winners ~2.3x losers, +74% / 2yr vs index
+8%, ~12% worst drawdown. EOD/delayed data, single market regime — trade small, a stop is mandatory.
"""

from __future__ import annotations

import argparse
import asyncio

from portfolio_backtest import MIN_AVG_VOL, WARMUP, _load
from scheme2_value import _fundamentals_at, _load_fundamentals
from schemes import _prep
from sqlalchemy import select

from bulls.core.db import get_sessionmaker
from bulls.core.models import CompanyProfile

STOP, TARGET = -0.10, 0.25
MAX_PE = 25  # quality gate: profitable and not expensive
MAX_SNAPSHOT_SESSIONS = 63


async def load_profiles(market):
    sm = get_sessionmaker()
    async with sm() as session:
        profs = list(
            await session.scalars(select(CompanyProfile).where(CompanyProfile.market == market))
        )
    return {p.code: p for p in profs}


def _qualifies(code, price, year, fin, div):
    """Returns (pe, roe) if profitable + cheap (the Scheme-3 quality gate), else None."""
    fa = _fundamentals_at(code, price, year, fin, div)
    if fa and fa[0] <= MAX_PE:  # fa = (pe, pb, roe, epsg, cons)
        return fa[0], fa[2]
    return None


# Validated backtest stats (scripts/portfolio_backtest.py + validate_scheme3.py) — the trust header.
TRACK_RECORD = {"total_2y": 73.6, "index_2y": 7.8, "win": 58, "maxdd": -12, "cagr": 31.7}


def build_scan_snapshot(
    by_code,
    fin,
    div,
    profs,
    *,
    max_sessions: int = MAX_SNAPSHOT_SESSIONS,
) -> dict:
    """Build the EOD read model used by the Hedge home and sizing pages.

    Recent trigger dates are retained as session offsets. The web process can therefore serve
    different look-back windows without loading bars or recomputing technical indicators.
    """
    max_sessions = max(1, int(max_sessions))
    latest = max(b.date for bars in by_code.values() for b in bars)

    candidates = []
    for code, bars in by_code.items():
        if len(bars) < WARMUP + 5 or sum(x.volume for x in bars[-20:]) / 20 < MIN_AVG_VOL:
            continue
        if (latest - bars[-1].date).days > 10:  # stale/delisted
            continue
        c, h, _r, _s20, _s200, _v20, hi, lo = _prep(bars)
        i = len(bars) - 1
        if not hi[i] or hi[i] <= lo[i]:
            continue
        below = (c[i] / hi[i] - 1) * 100
        pos = (c[i] - lo[i]) / (hi[i] - lo[i]) * 100
        if not (below < -40 and pos < 15):  # not in the launch zone today
            continue
        q = _qualifies(code, c[i], latest.year, fin, div)
        if not q:  # not profitable/cheap — Scheme-3 skips it (this is what saves us from junk)
            continue
        pe, roe = q
        px = c[i]
        # Conviction (0-100): the strategy's own thesis — deeper washout + cheaper + more profitable.
        # Used to rank the list so that, on days when more signals fire than you have room for, you
        # fund the strongest first instead of an arbitrary order.
        washout = min(abs(below), 80) / 80
        cheap = max(0.0, (25 - min(pe, 25)) / 25)
        qual = min(max(roe, 0), 30) / 30
        score = round((washout + cheap + qual) / 3 * 100)
        fires = [
            {
                "date": bars[j].date.isoformat(),
                "sessions_ago": i - j,
            }
            for j in range(max(5, len(bars) - max_sessions), len(bars))
            if c[j] > max(h[j - 5 : j])
        ]
        item = {
            "code": code,
            "price": round(px, 2),
            "stop": round(px * (1 + STOP), 2),
            "target": round(px * (1 + TARGET), 2),
            "pe": round(pe, 1),
            "roe": round(roe),
            "below_high": round(below),
            "score": score,
            "sector": (profs.get(code).sector if profs.get(code) else None) or "?",
            "fires": fires,
        }
        candidates.append(item)
    return {
        "as_of": latest.isoformat(),
        "max_sessions": max_sessions,
        "candidates": candidates,
        "track_record": TRACK_RECORD,
    }


def scan_from_snapshot(snapshot: dict, days: int = 5) -> dict:
    """Materialize one look-back window from a persisted EOD scan snapshot."""
    max_sessions = max(1, int(snapshot.get("max_sessions") or MAX_SNAPSHOT_SESSIONS))
    days = min(max(int(days), 1), max_sessions)
    fired, watch = [], []
    for candidate in snapshot.get("candidates", []):
        item = {key: value for key, value in candidate.items() if key != "fires"}
        fired_on = next(
            (
                fire["date"]
                for fire in candidate.get("fires", [])
                if int(fire["sessions_ago"]) < days
            ),
            None,
        )
        item["fired_on"] = fired_on
        (fired if fired_on else watch).append(item)

    # Rank by conviction (strongest first) so the top of the list is what to fund when room is tight;
    # recency breaks ties. The watchlist stays ordered by how close each is to firing.
    fired.sort(key=lambda r: (r["score"], r["fired_on"]), reverse=True)
    watch.sort(key=lambda r: r["score"], reverse=True)
    return {
        "as_of": snapshot["as_of"],
        "days": days,
        "fired": fired,
        "watch": watch,
        "track_record": snapshot.get("track_record", TRACK_RECORD),
        "ready": True,
    }


async def scan(days: int = 5) -> dict:
    """Compute today's Scheme-3 signals for CLI/offline use.

    HTTP requests use the persisted snapshot written by ``hedge_refresh.py`` instead.
    """
    by_code, _ = await _load()
    fin, div = await _load_fundamentals("DSE")
    profs = await load_profiles("DSE")
    return scan_from_snapshot(build_scan_snapshot(by_code, fin, div, profs), days)


async def _run(days):
    r = await scan(days)
    print(f"HEDGE — daily list · as of EOD {r['as_of']} · EOD/delayed · stop is mandatory\n")
    print(f"=== BUY signals (fired in last {days} session(s)): {len(r['fired'])} ===")
    if r["fired"]:
        print(
            f"  {'CODE':<11}{'entry':>8}{'stop':>8}{'target':>8}{'P/E':>6}{'ROE':>6}  why / sector"
        )
        for x in r["fired"]:
            print(
                f"  {x['code']:<11}{x['price']:>8.1f}{x['stop']:>8.1f}{x['target']:>8.1f}"
                f"{x['pe']:>6.1f}{x['roe']:>5}%  washed-out {x['below_high']:>3}%, cheap · {x['sector'][:18]}"
            )
    else:
        print("  (none today — the flagship is selective; see the watchlist)")
    print(f"\n=== WATCHLIST (zone + quality, waiting for the breakout): {len(r['watch'])} ===")
    print(f"  {'CODE':<11}{'price':>8}{'P/E':>6}{'ROE':>6}{'below_hi':>10}  sector")
    for x in r["watch"]:
        print(
            f"  {x['code']:<11}{x['price']:>8.1f}{x['pe']:>6.1f}{x['roe']:>5}%{x['below_high']:>9}%  {x['sector'][:18]}"
        )
    print(
        "\nHold ~2 weeks to 3 months (exit at +25% target, -10% stop, or 3 months). Risk ~1-2% of "
        "capital per name; ~10 positions. Low-cap names: size down (fills are rough)."
    )


def main():
    ap = argparse.ArgumentParser(
        description="Hedge daily morning list (Scheme-3 Quality Reversal)."
    )
    ap.add_argument("--days", type=int, default=5, help="look-back window for a fired breakout")
    asyncio.run(_run(ap.parse_args().days))


if __name__ == "__main__":
    main()
