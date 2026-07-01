"""Investor Lens for one symbol.

Different investment styles read the same DSE facts differently. This endpoint returns deterministic,
grounded persona-style reads without buy/sell calls or targets.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.deps import CurrentLocale, CurrentTenant, DbSession
from bulls.analytics import InvestorLensResponse, build_investor_lens
from bulls.core.models import QuoteSnapshot, Symbol, TickerAnalytics

router = APIRouter(tags=["investor-lens"])


@router.get("/symbols/{code}/investor-lens")
async def get_investor_lens(
    code: str, tenant: CurrentTenant, session: DbSession, locale: CurrentLocale
) -> InvestorLensResponse:
    code = code.upper()
    sym = await session.get(Symbol, (tenant.market, code))
    if sym is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")

    ta = await session.get(TickerAnalytics, (tenant.market, code))
    if ta is None:
        raise HTTPException(status_code=404, detail=f"No analytics for {code!r} yet")

    quote = await session.get(QuoteSnapshot, (tenant.market, code))
    adtv_mn = ta.avg_volume_20 * ta.last_close / 1e6 if ta.avg_volume_20 else None

    return build_investor_lens(
        code=code,
        as_of_date=str(ta.as_of_date),
        locale=locale,
        category=sym.category,
        pe_ratio=ta.pe_ratio,
        pb_ratio=ta.pb_ratio,
        pe_vs_sector=ta.pe_vs_sector,
        roe=ta.roe,
        eps_growth_yoy=ta.eps_growth_yoy,
        dividend_yield=ta.dividend_yield,
        above_sma_50=ta.above_sma_50,
        above_sma_200=ta.above_sma_200,
        mom_12_1=ta.mom_12_1,
        rsi_14=ta.rsi_14,
        relative_volume=ta.relative_volume,
        pct_from_52w_high=ta.pct_from_52w_high,
        institute_pct=ta.institute_pct,
        foreign_pct=ta.foreign_pct,
        institute_delta=ta.institute_delta,
        foreign_delta=ta.foreign_delta,
        cmf_20=ta.cmf_20,
        adtv_mn=adtv_mn,
        free_float_cap_mn=ta.free_float_cap_mn,
        volatility=ta.volatility,
        today_change_pct=quote.change_pct if quote else None,
    )
