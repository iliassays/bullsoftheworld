"""Stock Scorecard + Red Flags — a glanceable, transparent per-symbol summary for the Overview tab.

Reads the precomputed factor row (ticker_analytics) + the symbol's category, templates them into
independent 0-10 dimension scores and descriptive risk badges via bulls.analytics. Deterministic,
descriptive, no advice — and dimensions-only (no single composite verdict).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import CurrentLocale, CurrentTenant, DbSession, enforce_market_feature
from api.routers.market import load_freshest_quotes
from bulls.analytics import RedFlags, Scorecard, build_red_flags, build_scorecard
from bulls.core.markets import get_market_profile
from bulls.core.models import Symbol, TickerAnalytics

router = APIRouter(tags=["scorecard"])


class ScorecardResponse(BaseModel):
    scorecard: Scorecard
    red_flags: RedFlags


@router.get("/symbols/{code}/scorecard")
async def get_scorecard(
    code: str, tenant: CurrentTenant, session: DbSession, locale: CurrentLocale
) -> ScorecardResponse:
    enforce_market_feature(tenant, "interpreted_analytics")
    code = code.upper()
    sym = await session.get(Symbol, (tenant.market, code))
    if sym is None or not sym.is_retail_ready:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")
    ta = await session.get(TickerAnalytics, (tenant.market, code))
    if ta is None:
        raise HTTPException(status_code=404, detail=f"No analytics for {code!r} yet")

    adtv_mn = ta.avg_volume_20 * ta.last_close / 1e6 if ta.avg_volume_20 and ta.last_close else None
    profile = get_market_profile(tenant.market)
    quote = (
        await load_freshest_quotes(
            session,
            tenant.market,
            [code],
            profile.tz,
        )
    ).get(code)

    scorecard = build_scorecard(
        code=code,
        as_of_date=str(ta.as_of_date),
        locale=locale,
        above_sma_200=ta.above_sma_200,
        above_sma_50=ta.above_sma_50,
        mom_12_1=ta.mom_12_1,
        mom_6_1=ta.mom_6_1,
        mom_3_1=ta.mom_3_1,
        rsi_14=ta.rsi_14,
        roe=ta.roe,
        pe_ratio=ta.pe_ratio,
        pe_vs_sector=ta.pe_vs_sector,
        dividend_yield=ta.dividend_yield,
    )
    red_flags = build_red_flags(
        code=code,
        locale=locale,
        category=sym.category if profile.features.dse_categories else None,
        adtv_mn=adtv_mn,
        roe=ta.roe,
        dividend_yield=ta.dividend_yield,
        free_float_cap_mn=ta.free_float_cap_mn,
        today_change_pct=quote.change_pct if quote and profile.features.circuit_breakers else None,
    )
    return ScorecardResponse(scorecard=scorecard, red_flags=red_flags)
