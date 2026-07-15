"""Browse-by-size — canonical cap-tier lists for the retail browse page and SEO landing pages.

One cheap indexed query per request (ticker_analytics.cap_tier is denormalized by the analytics
run), so no Redis layer is needed. Tier vocabulary is per market (bulls.core.markets cap_tiers);
`unclassified` is a real, addressable bucket — names without a reliable market cap are shown
there, never guessed into a tier (omit-over-mislead).
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from api.deps import CurrentTenant, DbSession
from bulls.core.markets import get_market_profile
from bulls.core.models import QuoteSnapshot, Symbol, TickerAnalytics

router = APIRouter(tags=["browse"])

UNCLASSIFIED = "unclassified"


class TierCount(BaseModel):
    tier: str
    count: int


class BrowseItem(BaseModel):
    code: str
    name_en: str
    name_bn: str | None = None
    sector: str | None = None
    last_close: float | None = None
    change_pct: float | None = None
    market_cap_mn: float | None = None
    cap_tier: str | None = None  # None = unclassified


class BrowseSizeOut(BaseModel):
    market: str
    tier: str
    tiers: list[str]  # market's full tier vocabulary, largest first (drives the segmented header)
    as_of: dt.date | None  # analytics freshness — the UI must show it, never imply live data
    counts: list[TierCount]
    total: int  # rows in the requested tier
    items: list[BrowseItem]


def _visible_codes(market: str):
    return select(Symbol.code).where(
        Symbol.market == market,
        Symbol.is_active.is_(True),
        Symbol.is_hidden.is_(False),
        Symbol.data_status == "ready",
    )


@router.get("/browse/size/{tier}")
async def browse_size(
    tier: str,
    tenant: CurrentTenant,
    session: DbSession,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
) -> BrowseSizeOut:
    """One size tier's stocks, largest first, plus per-tier counts for the header.

    Descriptive browse only — ordering is by market cap, never by any score or view.
    """
    market = tenant.market
    tier_order = [name for name, _ in get_market_profile(market).cap_tiers]
    valid = [*tier_order, UNCLASSIFIED]
    if tier not in valid:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown size tier {tier!r} for {market}; expected one of {valid}",
        )

    T = TickerAnalytics
    visible = _visible_codes(market)
    count_rows = (
        await session.execute(
            select(T.cap_tier, func.count())
            .where(T.market == market, T.code.in_(visible))
            .group_by(T.cap_tier)
        )
    ).all()
    by_tier = {(t or UNCLASSIFIED): int(n) for t, n in count_rows}
    counts = [TierCount(tier=name, count=by_tier.get(name, 0)) for name in valid]

    tier_cond = T.cap_tier.is_(None) if tier == UNCLASSIFIED else T.cap_tier == tier
    rows = (
        await session.execute(
            select(
                T.code,
                Symbol.name_en,
                Symbol.name_bn,
                Symbol.sector,
                T.last_close,
                QuoteSnapshot.change_pct,
                T.market_cap_mn,
                T.cap_tier,
            )
            .join(Symbol, (Symbol.market == T.market) & (Symbol.code == T.code))
            .outerjoin(
                QuoteSnapshot,
                (QuoteSnapshot.market == T.market) & (QuoteSnapshot.code == T.code),
            )
            .where(T.market == market, T.code.in_(visible), tier_cond)
            .order_by(T.market_cap_mn.desc().nulls_last(), T.code.asc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    as_of = await session.scalar(
        select(func.max(T.as_of_date)).where(T.market == market, T.code.in_(visible))
    )

    return BrowseSizeOut(
        market=market,
        tier=tier,
        tiers=tier_order,
        as_of=as_of,
        counts=counts,
        total=by_tier.get(tier, 0),
        items=[
            BrowseItem(
                code=code,
                name_en=name_en,
                name_bn=name_bn,
                sector=sector,
                last_close=last_close,
                change_pct=change_pct,
                market_cap_mn=market_cap_mn,
                cap_tier=cap_tier,
            )
            for (
                code,
                name_en,
                name_bn,
                sector,
                last_close,
                change_pct,
                market_cap_mn,
                cap_tier,
            ) in rows
        ],
    )
