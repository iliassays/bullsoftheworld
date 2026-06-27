"""Compute the analytics snapshot for every symbol and persist it.

Runs after the EOD bar pull (in the scheduler), so the screener/dashboard reads a fresh
ticker_analytics row per symbol with plain SQL instead of recomputing on each request.

One-shot (cron-friendly / backfill now):
    uv run python -m ingestion.analytics DSE
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.analytics import compute, compute_valuation
from bulls.core.db import get_sessionmaker
from bulls.core.models import (
    AnnualFinancial,
    CompanyProfile,
    DailyBar,
    DividendRecord,
    SectorPE,
    ShareholdingSnapshot,
    Symbol,
    TickerAnalytics,
)

_LOOKBACK = 300  # enough for the 200-day SMA and 12-1 month momentum (needs ~253 bars)
_FIELDS = (
    "last_close",
    "sma_50",
    "sma_200",
    "above_sma_50",
    "above_sma_200",
    "rsi_14",
    "atr_14",
    "mom_3_1",
    "mom_6_1",
    "mom_12_1",
    "volatility",
    "nearest_support",
    "nearest_resistance",
    "week52_high",
    "week52_low",
    "pct_from_52w_high",
    "pct_from_52w_low",
    "avg_volume_20",
    "relative_volume",
    "cmf_20",
)
_VALUATION_FIELDS = (
    "market_cap_mn",
    "free_float_cap_mn",
    "pe_ratio",
    "pb_ratio",
    "dividend_yield",
    "roe",
)


_OWNERSHIP_FIELDS = (
    "sponsor_pct",
    "institute_pct",
    "foreign_pct",
    "public_pct",
    "institute_delta",
    "foreign_delta",
)
_EXTRA_FIELDS = ("pe_vs_sector", "eps_growth_yoy", *_OWNERSHIP_FIELDS)


def _valuation_row(
    last_close: float, profile: CompanyProfile | None, cash_dividend_pct: float | None
) -> dict[str, float | None]:
    """Derive the valuation fields from today's close + a symbol's fundamentals (None → all-None).

    `cash_dividend_pct` comes from the dividend-history table (latest declared year's cash), NOT
    profile.cash_dividend_pct — the latter is parsed from a label that can pick up a bonus issue.
    """
    if profile is None:
        return dict.fromkeys(_VALUATION_FIELDS)
    v = compute_valuation(
        last_close,
        outstanding_shares=profile.outstanding_shares,
        market_cap_mn_ref=profile.market_cap_mn,
        free_float_mcap_mn_ref=profile.free_float_mcap_mn,
        eps=profile.eps,
        nav_per_share=profile.nav_per_share,
        cash_dividend_pct=cash_dividend_pct,
        face_value=profile.face_value,
    )
    return {f: getattr(v, f) for f in _VALUATION_FIELDS}


async def _load_latest_cash_dividend(session, market: str) -> dict[str, float]:
    """Most recent declared year's cash dividend (% of face value), per code.

    Only the cash paid in a company's latest dividend year counts: if that latest year was
    bonus-only (a stock dividend), the company isn't currently a cash payer, so it's omitted rather
    than shown a years-old yield. This is the authoritative, correctly-typed source — unlike the
    'Latest Dividend Status' label, which can report a bonus figure as if it were cash.
    """
    rows = list(
        await session.scalars(
            select(DividendRecord)
            .where(DividendRecord.market == market)
            .order_by(DividendRecord.code, DividendRecord.year.desc())
        )
    )
    out: dict[str, float] = {}
    seen: set[str] = set()
    for r in rows:
        if r.code in seen:  # first row per code is its latest year
            continue
        seen.add(r.code)
        if r.cash_pct and r.cash_pct > 0:
            out[r.code] = r.cash_pct
    return out


async def _load_ownership(session, market: str) -> dict[str, dict[str, float | None]]:
    """Latest shareholding % per code + month-over-month delta vs the prior snapshot."""
    rows = list(
        await session.scalars(
            select(ShareholdingSnapshot)
            .where(ShareholdingSnapshot.market == market)
            .order_by(ShareholdingSnapshot.code, ShareholdingSnapshot.as_of_date.desc())
        )
    )
    by_code: dict[str, list[ShareholdingSnapshot]] = {}
    for r in rows:
        by_code.setdefault(r.code, []).append(r)  # already newest-first per code
    out: dict[str, dict[str, float | None]] = {}
    for code, snaps in by_code.items():
        cur = snaps[0]
        prev = snaps[1] if len(snaps) > 1 else None
        out[code] = {
            "sponsor_pct": cur.sponsor_director,
            "institute_pct": cur.institute,
            "foreign_pct": cur.foreign_pct,
            "public_pct": cur.public,
            "institute_delta": _delta(cur.institute, prev and prev.institute),
            "foreign_delta": _delta(cur.foreign_pct, prev and prev.foreign_pct),
        }
    return out


async def _load_eps_growth(session, market: str) -> dict[str, float]:
    """YoY EPS growth (%) from the two most recent fiscal years, per code."""
    rows = list(
        await session.scalars(
            select(AnnualFinancial)
            .where(AnnualFinancial.market == market)
            .order_by(AnnualFinancial.code, AnnualFinancial.fiscal_year.desc())
        )
    )
    by_code: dict[str, list[AnnualFinancial]] = {}
    for r in rows:
        by_code.setdefault(r.code, []).append(r)
    out: dict[str, float] = {}
    for code, fins in by_code.items():
        if len(fins) >= 2 and fins[0].eps is not None and fins[1].eps:
            out[code] = round((fins[0].eps - fins[1].eps) / abs(fins[1].eps) * 100, 2)
    return out


def _delta(cur: float | None, prev: float | None) -> float | None:
    return None if cur is None or prev is None else round(cur - prev, 2)


def _extra_row(
    code: str,
    pe_ratio: float | None,
    sector: str | None,
    sector_pe: dict[str, float],
    ownership: dict[str, dict[str, float | None]],
    eps_growth: dict[str, float],
) -> dict[str, float | None]:
    """Ownership %, EPS growth, and sector-relative P/E for one symbol."""
    row: dict[str, float | None] = dict.fromkeys(_EXTRA_FIELDS)
    row.update(ownership.get(code, {}))
    row["eps_growth_yoy"] = eps_growth.get(code)
    median = sector_pe.get(sector) if sector else None
    if pe_ratio is not None and median and median > 0:
        row["pe_vs_sector"] = round(pe_ratio / median, 2)
    return row


async def compute_all(market: str) -> dict[str, int]:
    """Compute + upsert analytics for every symbol with price history. Returns counts."""
    sm = get_sessionmaker()
    async with sm() as session:
        codes = list(await session.scalars(select(Symbol.code).where(Symbol.market == market)))
        # Fundamentals for daily valuation — keyed by code, from the weekly company scrape.
        profiles = {
            p.code: p
            for p in await session.scalars(
                select(CompanyProfile).where(CompanyProfile.market == market)
            )
        }
        sector_pe = dict(
            (
                await session.execute(
                    select(SectorPE.sector, SectorPE.median_pe).where(SectorPE.market == market)
                )
            ).all()
        )
        ownership = await _load_ownership(session, market)
        eps_growth = await _load_eps_growth(session, market)
        cash_dividends = await _load_latest_cash_dividend(session, market)

    computed = 0
    async with sm() as session:
        for code in codes:
            bars = list(
                await session.scalars(
                    select(DailyBar)
                    .where(DailyBar.market == market, DailyBar.code == code)
                    .order_by(DailyBar.date.desc())
                    .limit(_LOOKBACK)
                )
            )
            if not bars:
                continue
            result = compute(list(reversed(bars)))
            profile = profiles.get(code)
            row = {"market": market, "code": code, "as_of_date": result.as_of_date}
            row.update({f: getattr(result, f) for f in _FIELDS})
            row.update(_valuation_row(result.last_close, profile, cash_dividends.get(code)))
            row.update(
                _extra_row(
                    code,
                    row["pe_ratio"],
                    profile.sector if profile else None,
                    sector_pe,
                    ownership,
                    eps_growth,
                )
            )

            stmt = pg_insert(TickerAnalytics).values(row)
            update_cols = {c: getattr(stmt.excluded, c) for c in row if c not in ("market", "code")}
            stmt = stmt.on_conflict_do_update(index_elements=["market", "code"], set_=update_cols)
            await session.execute(stmt)
            computed += 1
        await session.commit()

    return {"symbols": len(codes), "computed": computed}


async def _run(market: str) -> None:
    counts = await compute_all(market)
    print(f"[analytics] {market}: computed {counts['computed']}/{counts['symbols']} symbols")


def main() -> None:
    market = sys.argv[1] if len(sys.argv) > 1 else "DSE"
    asyncio.run(_run(market))


if __name__ == "__main__":
    main()
