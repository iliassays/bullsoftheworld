"""Daily Shortlist — the always-full daily research slate.

Replaces an empty screen with five names a researcher can actually start on. Scheme-3's four
boolean gates align on only 21.6% of DSE sessions, so the `quality_reversal_eod` board is blank
78% of the time; this ranks the eligible universe instead of demanding every gate pass, and is
therefore never empty when the market traded.

Descriptive only, and the response is built so it cannot be misread as a tip sheet:
``is_return_claim`` is always false, and the measured base rates travel with every payload — over
232 tested DSE sessions a return-seeking rank did 1.24pp *worse* than a random draw from the same
pool. See ``docs/research/dse-daily-slate-study-2026-07-25.md``.

Freshness is explicit per the platform rule: the slate carries the analytics session date, the
quote timestamp and ``is_delayed``, so the UI can never present a stale slate as live.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select

from api.deps import CurrentTenant, DbSession, enforce_market_feature
from bulls.analytics.daily_shortlist import (
    METHODOLOGY_VERSION,
    ShortlistCandidate,
    build_daily_shortlist,
)
from bulls.core.models import CompanyProfile, QuoteSnapshot, Symbol, TickerAnalytics

router = APIRouter(tags=["shortlist"])

MAX_SIZE = 10


class ShortlistFactOut(BaseModel):
    """A localisable statement: the client renders ``kind`` in the reader's language."""

    kind: str
    value: float | None = None


class ShortlistRow(BaseModel):
    code: str
    # Both names are returned and the client picks, matching /browse — no server-side locale
    # branching, so a Bangla and an English reader get the same payload.
    name_en: str | None = None
    name_bn: str | None = None
    rank: int
    attention_score: float
    close: float
    change_pct: float | None = None
    sector: str | None = None
    pe: float | None = None
    # Structured for localisation; reasons/unknowns are the English renderings of the same facts,
    # kept so an English tenant and non-UI consumers do not have to re-implement the wording.
    facts: list[ShortlistFactOut]
    cautions: list[ShortlistFactOut]
    reasons: list[str]
    unknowns: list[str]


class ShortlistResponse(BaseModel):
    market: str
    as_of: dt.date
    quote_as_of: dt.datetime | None = None
    is_delayed: bool = True
    size: int
    rows: list[ShortlistRow]
    eligible_names: int
    excluded_illiquid: int
    excluded_short_history: int
    # Always false. The slate ranks attention, never expected return.
    is_return_claim: bool = False
    methodology_version: str = METHODOLOGY_VERSION
    base_rates: dict
    notes: list[str]


def _range_position_pct(row: TickerAnalytics) -> float | None:
    """Where the close sits in the 52-week range, 0 = at the low, 100 = at the high."""
    if row.week52_high is None or row.week52_low is None:
        return None
    span = row.week52_high - row.week52_low
    if span <= 0:
        return None
    return (row.last_close - row.week52_low) / span * 100.0


@router.get("/shortlist/daily")
async def daily_shortlist(
    tenant: CurrentTenant,
    session: DbSession,
    size: int = Query(5, ge=1, le=MAX_SIZE),
) -> ShortlistResponse:
    enforce_market_feature(tenant, "interpreted_analytics")
    market = tenant.market

    latest_date = (
        select(func.max(TickerAnalytics.as_of_date))
        .where(TickerAnalytics.market == market)
        .scalar_subquery()
    )
    # Visible, active, non-Z symbols on the freshest analytics session — the same cleanliness
    # rule the scanner boards use, so the two surfaces cannot disagree about the universe.
    stmt = (
        select(
            TickerAnalytics, Symbol.name_en, Symbol.name_bn, CompanyProfile.sector, QuoteSnapshot
        )
        .join(
            Symbol,
            and_(Symbol.market == TickerAnalytics.market, Symbol.code == TickerAnalytics.code),
        )
        .join(
            CompanyProfile,
            and_(
                CompanyProfile.market == TickerAnalytics.market,
                CompanyProfile.code == TickerAnalytics.code,
            ),
            isouter=True,
        )
        .join(
            QuoteSnapshot,
            and_(
                QuoteSnapshot.market == TickerAnalytics.market,
                QuoteSnapshot.code == TickerAnalytics.code,
            ),
            isouter=True,
        )
        .where(
            TickerAnalytics.market == market,
            TickerAnalytics.as_of_date == latest_date,
            Symbol.is_active.is_(True),
            Symbol.is_hidden.is_(False),
            Symbol.data_status == "ready",
            (Symbol.category.is_(None)) | (Symbol.category != "Z"),
            TickerAnalytics.last_close > 0,
            # Seasoning proxy: both require a long history, so their presence stands in for the
            # module's bar count, which ticker_analytics does not store.
            TickerAnalytics.sma_200.is_not(None),
            TickerAnalytics.week52_high.is_not(None),
        )
    )

    rows = (await session.execute(stmt)).all()
    names: dict[str, tuple[str | None, str | None]] = {}
    candidates: list[ShortlistCandidate] = []
    as_of = dt.date.today()
    quote_as_of: dt.datetime | None = None
    is_delayed = True

    for analytics, name_en, name_bn, sector, quote in rows:
        as_of = analytics.as_of_date
        names[analytics.code] = (name_en, name_bn)
        if quote is not None and (quote_as_of is None or quote.as_of > quote_as_of):
            quote_as_of = quote.as_of
            is_delayed = quote.is_delayed
        volume = None
        if analytics.relative_volume is not None and analytics.avg_volume_20:
            volume = analytics.relative_volume * analytics.avg_volume_20
        candidates.append(
            ShortlistCandidate(
                code=analytics.code,
                close=analytics.last_close,
                avg_volume_20=analytics.avg_volume_20,
                # None: the SQL seasoning gate above already enforced history.
                bars_seen=None,
                change_pct=quote.change_pct if quote is not None else None,
                volume=volume,
                pct_from_52w_high=analytics.pct_from_52w_high,
                range_position_pct=_range_position_pct(analytics),
                sma_200=analytics.sma_200,
                # pe_ratio is NULL when EPS <= 0, so a present ratio implies positive earnings.
                eps=1.0 if analytics.pe_ratio is not None else None,
                nav_per_share=1.0 if analytics.pb_ratio is not None else None,
                pe=analytics.pe_ratio,
                sector=sector,
            )
        )

    slate = build_daily_shortlist(candidates, market=market, as_of=as_of, size=size)
    return ShortlistResponse(
        market=slate.market,
        as_of=slate.as_of,
        quote_as_of=quote_as_of,
        is_delayed=is_delayed,
        size=slate.size,
        rows=[
            ShortlistRow(
                code=entry.code,
                name_en=names.get(entry.code, (None, None))[0],
                name_bn=names.get(entry.code, (None, None))[1],
                rank=entry.rank,
                attention_score=entry.attention_score,
                close=entry.close,
                change_pct=entry.change_pct,
                sector=entry.sector,
                pe=entry.pe,
                facts=[ShortlistFactOut(kind=f.kind, value=f.value) for f in entry.facts],
                cautions=[ShortlistFactOut(kind=c.kind, value=c.value) for c in entry.cautions],
                reasons=entry.reasons,
                unknowns=entry.unknowns,
            )
            for entry in slate.entries
        ],
        eligible_names=slate.eligible_names,
        excluded_illiquid=slate.excluded_illiquid,
        excluded_short_history=slate.excluded_short_history,
        is_return_claim=slate.is_return_claim,
        methodology_version=slate.methodology_version,
        base_rates=slate.base_rates,
        notes=slate.notes,
    )
