"""Hedge — the frozen legacy Scheme-3 Quality Reversal monitor.

Scans the latest EOD data for names that meet the historical Scheme-3 rule — a washed-out,
profitable, cheap company turning up — and prints each with its signal reference, stop, target and
quality context. It also preserves the pre-trigger watchlist. Hedge is not the Atlas portfolio
authority and this monitor does not create an Atlas target, order or fill.

    uv run python scripts/hedge_daily.py            # this EOD's new signals + watchlist

The separate History page reads a dynamically computed legacy diagnostic. Its same-close,
single-regime methodology is exploratory and is not an institutional or forward-paper track record.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt

from hedge_forward import build_rows
from portfolio_backtest import MIN_AVG_VOL, WARMUP, _load
from scheme2_value import _fundamentals_at, _load_fundamentals
from scheme_lab import quality_reversal
from schemes import _prep
from sqlalchemy import select

from bulls.core.db import get_sessionmaker
from bulls.core.models import CompanyProfile

STOP, TARGET = -0.10, 0.25
MAX_PE = 25  # quality gate: profitable and not expensive


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


LEGACY_RESEARCH_STATUS = {
    "authority": "frozen_legacy_monitor",
    "performance_source": "persisted_dynamic_history",
    "performance_surface": "/history",
    "atlas_book": False,
}


def _current_setup_rows(
    by_code,
    fin,
    div,
    profs,
) -> tuple[dt.date, dict[str, dict]]:
    """Current launch-zone rows, including names that fired on this session."""
    latest = max(b.date for bars in by_code.values() for b in bars)
    candidates: dict[str, dict] = {}
    for code, bars in by_code.items():
        if len(bars) < WARMUP + 5 or sum(x.volume for x in bars[-20:]) / 20 < MIN_AVG_VOL:
            continue
        if bars[-1].date != latest:
            # A point-in-time publication must not present an older close as today's setup.
            continue
        c, _h, _r, _s20, _s200, _v20, hi, lo = _prep(bars)
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
        candidates[code] = {
            "code": code,
            "price": round(px, 2),
            "stop": round(px * (1 + STOP), 2),
            "target": round(px * (1 + TARGET), 2),
            "pe": round(pe, 1),
            "roe": round(roe),
            "below_high": round(below),
            "score": score,
            "sector": (profs.get(code).sector if profs.get(code) else None) or "?",
        }
    return latest, candidates


def _active_signal_rows(by_code, ledger_rows: list[dict], latest: dt.date) -> list[dict]:
    active = []
    for signal in ledger_rows:
        if signal["status"] != "open" or signal["signal_date"] == latest:
            continue
        bars = by_code.get(signal["code"], [])
        current = next((bar.close for bar in reversed(bars) if bar.date <= latest), None)
        if current is None:
            continue
        entry = signal["entry"]
        active.append(
            {
                "code": signal["code"],
                "signal_date": signal["signal_date"].isoformat(),
                "entry": entry,
                "stop": signal["stop"],
                "target": signal["target"],
                "price": round(current, 2),
                "return_pct": round((current / entry - 1) * 100, 1),
            }
        )
    active.sort(key=lambda row: (row["signal_date"], row["code"]), reverse=True)
    return active


def _monitor_codes(payload: dict | None) -> set[str]:
    if not payload:
        return set()
    return {
        row["code"]
        for key in ("new_signals", "active_signals", "watchlist")
        for row in payload.get(key, [])
    }


def classify_monitor_changes(
    *,
    new_signals: list[dict],
    active_signals: list[dict],
    watchlist: list[dict],
    previous: dict | None,
) -> dict:
    current_codes = {row["code"] for row in [*new_signals, *active_signals, *watchlist]}
    previous_codes = _monitor_codes(previous)
    return {
        "added": sorted(current_codes - previous_codes),
        "continued": sorted(current_codes & previous_codes),
        "removed": sorted(previous_codes - current_codes),
        "has_prior_session": previous is not None,
    }


def build_scan_snapshot(
    by_code,
    fin,
    div,
    profs,
    signals,
    ledger_rows: list[dict],
    *,
    previous: dict | None = None,
) -> dict:
    """Build one point-in-time, session-specific Quality Reversal publication."""
    latest, current_setups = _current_setup_rows(by_code, fin, div, profs)
    new_signals = []
    for code in sorted(signals):
        if latest not in signals[code]:
            continue
        item = current_setups.get(code)
        if item is None:
            continue
        new_signals.append({**item, "fired_on": latest.isoformat()})
    new_signals.sort(key=lambda row: (row["score"], row["code"]), reverse=True)

    new_codes = {row["code"] for row in new_signals}
    watchlist = [row for code, row in current_setups.items() if code not in new_codes]
    watchlist.sort(key=lambda row: (row["score"], row["code"]), reverse=True)
    active_signals = _active_signal_rows(by_code, ledger_rows, latest)

    return {
        "schema_version": 1,
        "as_of": latest.isoformat(),
        "new_signals": new_signals,
        "active_signals": active_signals,
        "watchlist": watchlist,
        "changes": classify_monitor_changes(
            new_signals=new_signals,
            active_signals=active_signals,
            watchlist=watchlist,
            previous=previous,
        ),
        "research_status": LEGACY_RESEARCH_STATUS,
    }


def scan_from_snapshot(snapshot: dict) -> dict:
    """Compatibility shape consumed by the Hedge list, sizing page, and signals API."""
    return {
        "as_of": snapshot["as_of"],
        "fired": snapshot.get("new_signals", []),
        "watch": snapshot.get("watchlist", []),
        "active": snapshot.get("active_signals", []),
        "changes": snapshot.get("changes", {}),
        # Old immutable publications contain a hard-coded ``track_record`` object. Do not project
        # that stale claim into the current view; performance belongs to the dynamic History read.
        "research_status": snapshot.get("research_status", LEGACY_RESEARCH_STATUS),
        "ready": True,
    }


async def scan() -> dict:
    """Compute today's Scheme-3 signals for CLI/offline use.

    HTTP requests use the persisted snapshot written by ``hedge_refresh.py`` instead.
    """
    by_code, _ = await _load()
    fin, div = await _load_fundamentals("DSE")
    profs = await load_profiles("DSE")
    signals = quality_reversal(by_code, fin, div)
    return scan_from_snapshot(
        build_scan_snapshot(
            by_code,
            fin,
            div,
            profs,
            signals,
            build_rows(by_code, signals),
        )
    )


async def _run():
    r = await scan()
    print(f"HEDGE — daily list · as of EOD {r['as_of']} · EOD/delayed · stop is mandatory\n")
    print(f"=== NEW BUY signals this session: {len(r['fired'])} ===")
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
        print("  (none today — the frozen rule is selective; see the watchlist)")
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
    ap.parse_args()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
