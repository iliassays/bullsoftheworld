"""Compute the analytics snapshot for every symbol and persist it.

Runs after the EOD bar pull (in the scheduler), so the screener/dashboard reads a fresh
ticker_analytics row per symbol with plain SQL instead of recomputing on each request.

One-shot (cron-friendly / backfill now):
    uv run python -m ingestion.analytics DSE
"""

from __future__ import annotations

import asyncio
import datetime as dt
import statistics
import sys
from collections import defaultdict
from types import SimpleNamespace

from sqlalchemy import delete, exists, func, select, true, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.analytics import adjust_bars, compute, compute_valuation, detect_patterns
from bulls.core.db import get_sessionmaker
from bulls.core.markets import cap_tier
from bulls.core.models import (
    AnnualFinancial,
    CompanyProfile,
    DailyBar,
    DividendRecord,
    SectorPE,
    ShareholdingSnapshot,
    Symbol,
    TickerAnalytics,
    TickerPattern,
)

_LOOKBACK = 300  # enough for the 200-day SMA and 12-1 month momentum (needs ~253 bars)
_BATCH_SIZE = 250
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
    "rel_volume_5d",
    "rel_volume_1m",
    "cmf_20",
    "obv_slope",
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
    last_close: float,
    profile: CompanyProfile | None,
    cash_dividend: tuple[float | None, float | None] | None,
) -> dict[str, float | None]:
    """Derive the valuation fields from today's close + a symbol's fundamentals (None → all-None).

    `cash_dividend_pct` comes from the dividend-history table (latest declared year's cash), NOT
    profile.cash_dividend_pct — the latter is parsed from a label that can pick up a bonus issue.
    """
    if profile is None:
        return dict.fromkeys(_VALUATION_FIELDS)
    cash_pct, cash_per_share = cash_dividend or (None, None)
    v = compute_valuation(
        last_close,
        outstanding_shares=profile.outstanding_shares,
        market_cap_mn_ref=profile.market_cap_mn,
        free_float_mcap_mn_ref=profile.free_float_mcap_mn,
        eps=profile.eps,
        nav_per_share=profile.nav_per_share,
        cash_dividend_pct=cash_pct,
        cash_dividend_per_share=cash_per_share,
        face_value=profile.face_value,
    )
    return {f: getattr(v, f) for f in _VALUATION_FIELDS}


async def _load_latest_cash_dividend(
    session, market: str, *, as_of_year: int | None = None
) -> dict[str, tuple[float | None, float | None]]:
    """Most recent declared year's cash dividend (% of face value), per code.

    Only the cash paid in a company's latest dividend year counts: if that latest year was
    bonus-only (a stock dividend), the company isn't currently a cash payer, so it's omitted rather
    than shown a years-old yield. This is the authoritative, correctly-typed source — unlike the
    'Latest Dividend Status' label, which can report a bonus figure as if it were cash.
    """
    as_of_year = as_of_year or dt.date.today().year
    rows = list(
        await session.scalars(
            select(DividendRecord)
            .where(DividendRecord.market == market)
            .order_by(DividendRecord.code, DividendRecord.year.desc())
        )
    )
    out: dict[str, tuple[float | None, float | None]] = {}
    seen: set[str] = set()
    for r in rows:
        if r.code in seen:  # first row per code is its latest year
            continue
        seen.add(r.code)
        # A historical payment is useful history, but must not become a current yield. Allow the
        # current/prior reporting year because many issuers declare after their fiscal year closes.
        if not _is_current_dividend_year(r.year, as_of_year):
            continue
        if (r.cash_pct and r.cash_pct > 0) or (r.cash_per_share and r.cash_per_share > 0):
            out[r.code] = (r.cash_pct, r.cash_per_share)
    return out


def _is_current_dividend_year(dividend_year: int, as_of_year: int) -> bool:
    """Current yield may use only the current or immediately preceding reporting year."""
    return as_of_year - 1 <= dividend_year <= as_of_year


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
        if len(fins) >= 2:
            growth = _comparable_eps_growth(fins[0].eps, fins[1].eps)
            if growth is not None:
                out[code] = growth
    return out


def _comparable_eps_growth(current: float | None, prior: float | None) -> float | None:
    """YoY percentage growth is meaningful only from a positive earnings base.

    Loss-to-profit and loss-to-smaller-loss cases are turnarounds, not percentage growth. Returning
    None keeps them out of growth rankings until a dedicated turnaround feature can label them.
    """
    if current is None or prior is None or prior <= 0:
        return None
    return round((current - prior) / prior * 100, 2)


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


async def _load_bar_batch(session, market: str, codes: list[str]) -> dict[str, list]:
    """Load the latest lookback per code in one windowed query."""
    ranked = (
        select(
            DailyBar.code.label("code"),
            DailyBar.date.label("date"),
            DailyBar.open.label("open"),
            DailyBar.high.label("high"),
            DailyBar.low.label("low"),
            DailyBar.close.label("close"),
            DailyBar.volume.label("volume"),
            DailyBar.adjusted_close.label("adjusted_close"),
            func.row_number()
            .over(partition_by=DailyBar.code, order_by=DailyBar.date.desc())
            .label("row_num"),
        )
        .where(DailyBar.market == market, DailyBar.code.in_(codes))
        .subquery()
    )
    rows = (
        await session.execute(
            select(ranked)
            .where(ranked.c.row_num <= _LOOKBACK)
            .order_by(ranked.c.code, ranked.c.date)
        )
    ).mappings()
    grouped: dict[str, list] = defaultdict(list)
    for row in rows:
        grouped[row["code"]].append(
            SimpleNamespace(
                market=market,
                code=row["code"],
                date=row["date"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                adjusted_close=row["adjusted_close"],
            )
        )
    return grouped


async def _persist_symbol_analytics(
    session,
    market: str,
    code: str,
    bars: list,
    profiles,
    cash_dividends,
    sector_pe,
    ownership,
    eps_growth,
) -> tuple[int, int]:
    if not bars:
        return 0, 0
    ascending = adjust_bars(bars)
    result = compute(ascending)
    profile = profiles.get(code)
    row = {"market": market, "code": code, "as_of_date": result.as_of_date}
    row.update({field: getattr(result, field) for field in _FIELDS})
    # Indicators use split/distribution-adjusted bars; valuation must use the listed security's
    # unadjusted current close against its current per-share fundamentals.
    row.update(_valuation_row(bars[-1].close, profile, cash_dividends.get(code)))
    # Canonical size tier follows the freshly computed cap — NULL (unclassified) when unknown.
    row["cap_tier"] = cap_tier(row["market_cap_mn"], market)
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
    update_cols = {col: getattr(stmt.excluded, col) for col in row if col not in ("market", "code")}
    await session.execute(
        stmt.on_conflict_do_update(index_elements=["market", "code"], set_=update_cols)
    )

    matches = detect_patterns(ascending)
    if not matches:
        await session.execute(
            delete(TickerPattern).where(TickerPattern.market == market, TickerPattern.code == code)
        )
        return 1, 0

    match = matches[0]
    pattern_row = {
        "market": market,
        "code": code,
        "as_of_date": result.as_of_date,
        "pattern_type": match.pattern_type,
        "status": match.status,
        "start_date": match.start_date,
        "end_date": match.end_date,
        "breakout_date": match.breakout_date,
        "strength_score": match.strength_score,
        "payload": match.model_dump(mode="json"),
    }
    pattern_stmt = pg_insert(TickerPattern).values(pattern_row)
    pattern_updates = {
        col: getattr(pattern_stmt.excluded, col)
        for col in pattern_row
        if col not in ("market", "code")
    }
    await session.execute(
        pattern_stmt.on_conflict_do_update(index_elements=["market", "code"], set_=pattern_updates)
    )
    return 1, 1


async def compute_all(
    market: str,
    *,
    codes: list[str] | None = None,
    include_onboarding: bool = False,
    include_restricted: bool = False,
) -> dict[str, int]:
    """Compute + upsert analytics for every symbol with price history. Returns counts."""
    if include_restricted and not codes:
        raise ValueError("include_restricted requires an explicit non-empty code list")
    sm = get_sessionmaker()
    async with sm() as session:
        statuses = (
            ("ready", "onboarding", "research_only", "degraded")
            if include_restricted
            else ("ready", "onboarding")
            if include_onboarding
            else ("ready",)
        )
        code_rows = list(
            await session.scalars(
                select(Symbol.code).where(
                    Symbol.market == market,
                    Symbol.is_active.is_(True),
                    true() if include_restricted else Symbol.is_hidden.is_(False),
                    Symbol.data_status.in_(statuses),
                    Symbol.code.in_(codes) if codes is not None else True,
                    exists().where(
                        DailyBar.market == market,
                        DailyBar.code == Symbol.code,
                    ),
                )
            )
        )
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
    patterns_found = 0
    async with sm() as session:
        for start in range(0, len(code_rows), _BATCH_SIZE):
            batch = code_rows[start : start + _BATCH_SIZE]
            bars_by_code = await _load_bar_batch(session, market, batch)
            for code in batch:
                done, patterns = await _persist_symbol_analytics(
                    session,
                    market,
                    code,
                    bars_by_code.get(code, []),
                    profiles,
                    cash_dividends,
                    sector_pe,
                    ownership,
                    eps_growth,
                )
                computed += done
                patterns_found += patterns
            await session.commit()

    if market.upper() != "DSE":
        async with sm() as session:
            rows = (
                await session.execute(
                    select(CompanyProfile.sector, TickerAnalytics.code, TickerAnalytics.pe_ratio)
                    .join(
                        TickerAnalytics,
                        (TickerAnalytics.market == CompanyProfile.market)
                        & (TickerAnalytics.code == CompanyProfile.code),
                    )
                    .where(
                        CompanyProfile.market == market,
                        CompanyProfile.sector.isnot(None),
                        TickerAnalytics.pe_ratio > 0,
                    )
                )
            ).all()
            by_sector: dict[str, list[float]] = defaultdict(list)
            for sector, _, pe in rows:
                by_sector[sector].append(float(pe))
            medians = {
                sector: statistics.median(values)
                for sector, values in by_sector.items()
                if len(values) >= 3
            }
            now = dt.datetime.now(dt.UTC)
            if medians:
                stmt = pg_insert(SectorPE).values(
                    [
                        {
                            "market": market,
                            "sector": sector,
                            "median_pe": median,
                            "fetched_at": now,
                        }
                        for sector, median in medians.items()
                    ]
                )
                await session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["market", "sector"],
                        set_={
                            "median_pe": stmt.excluded.median_pe,
                            "fetched_at": stmt.excluded.fetched_at,
                        },
                    )
                )
                for sector, code, pe in rows:
                    median = medians.get(sector)
                    if median:
                        await session.execute(
                            update(TickerAnalytics)
                            .where(
                                TickerAnalytics.market == market,
                                TickerAnalytics.code == code,
                            )
                            .values(pe_vs_sector=round(float(pe) / median, 2))
                        )
            await session.commit()

    return {"symbols": len(code_rows), "computed": computed, "patterns": patterns_found}


async def _run(market: str) -> None:
    counts = await compute_all(market)
    print(
        f"[analytics] {market}: computed {counts['computed']}/{counts['symbols']} symbols, "
        f"{counts['patterns']} chart patterns"
    )


def main() -> None:
    market = sys.argv[1] if len(sys.argv) > 1 else "DSE"
    asyncio.run(_run(market))


if __name__ == "__main__":
    main()
