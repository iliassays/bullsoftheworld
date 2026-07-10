"""Plain read — a synthesised, readable profile of one symbol for the Overview tab.

Reads the precomputed factor row (ticker_analytics) and templates it into plain sentences + a "how
traders read this" framing via bulls.analytics.build_plain_read. Deterministic, descriptive, no
advice — the bridge from 20 disconnected numbers to something a trader can reason about.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import CurrentLocale, CurrentTenant, DbSession, enforce_market_feature
from bulls.analytics import build_plain_read
from bulls.core.models import Symbol, TickerAnalytics

router = APIRouter(tags=["plain-read"])


class ReadPointOut(BaseModel):
    tag: str
    text: str


class PlainReadResponse(BaseModel):
    code: str
    as_of_date: str
    headline: str
    points: list[ReadPointOut]
    how_to_read: str
    disclaimer: str


@router.get("/symbols/{code}/plain-read")
async def get_plain_read(
    code: str, tenant: CurrentTenant, session: DbSession, locale: CurrentLocale
) -> PlainReadResponse:
    enforce_market_feature(tenant, "interpreted_analytics")
    code = code.upper()
    symbol = await session.get(Symbol, (tenant.market, code))
    if symbol is None or not symbol.is_retail_ready:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")
    ta = await session.get(TickerAnalytics, (tenant.market, code))
    if ta is None:
        raise HTTPException(status_code=404, detail=f"No analytics for {code!r} yet")

    adtv_mn = ta.avg_volume_20 * ta.last_close / 1e6 if ta.avg_volume_20 and ta.last_close else None
    read = build_plain_read(
        code=code,
        as_of_date=str(ta.as_of_date),
        locale=locale,
        market_cap_mn=ta.market_cap_mn,
        adtv_mn=adtv_mn,
        above_sma_200=ta.above_sma_200,
        mom_12_1=ta.mom_12_1,
        volatility=ta.volatility,
        roe=ta.roe,
        pe_ratio=ta.pe_ratio,
        pe_vs_sector=ta.pe_vs_sector,
        dividend_yield=ta.dividend_yield,
        rsi_14=ta.rsi_14,
        pct_from_52w_high=ta.pct_from_52w_high,
        pct_from_52w_low=ta.pct_from_52w_low,
        cmf_20=ta.cmf_20,
        institute_delta=ta.institute_delta,
        foreign_delta=ta.foreign_delta,
    )
    return PlainReadResponse(**read.model_dump())
