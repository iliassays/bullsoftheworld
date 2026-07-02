"""Investor Lens for one symbol.

Different investment styles read the same DSE facts differently. This endpoint returns deterministic,
grounded persona-style reads without buy/sell calls or targets.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from api.deps import CurrentLocale, CurrentTenant, DbSession
from bulls.analytics import InvestorLensResponse, build_investor_lens
from bulls.core.models import (
    Announcement,
    CompanyProfile,
    QuoteSnapshot,
    Symbol,
    TickerAnalytics,
)

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

    # Balance-sheet leverage from the company profile (loans vs book equity), so the lenses can SHOW
    # debt instead of punting it. Skipped when the profile lacks loan data.
    cp = await session.get(CompanyProfile, (tenant.market, code))
    debt_to_equity: float | None = None
    credit_rating: str | None = None
    if cp is not None:
        credit_rating = cp.credit_rating_long
        has_loan = cp.short_term_loan_mn is not None or cp.long_term_loan_mn is not None
        equity = (cp.paid_up_capital_mn or 0) + (cp.reserve_surplus_mn or 0) + (cp.oci_mn or 0)
        if has_loan and equity > 0:
            debt_to_equity = ((cp.short_term_loan_mn or 0) + (cp.long_term_loan_mn or 0)) / equity

    # Recent material announcements (last 30 days) — so the lens can say "2 recent (dividend)" or
    # "none", instead of telling the user to go hunt the news themselves.
    since = ta.as_of_date - dt.timedelta(days=30)
    news = list(
        await session.scalars(
            select(Announcement)
            .where(
                Announcement.market == tenant.market,
                Announcement.code == code,
                Announcement.published_at >= since,
            )
            .order_by(Announcement.published_at.desc())
        )
    )

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
        debt_to_equity=debt_to_equity,
        credit_rating=credit_rating,
        nearest_support=ta.nearest_support,
        nearest_resistance=ta.nearest_resistance,
        last_close=ta.last_close,
        recent_news_count=len(news),
        recent_news_label=news[0].category if news else None,
    )
