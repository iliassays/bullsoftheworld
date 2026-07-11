"""Investor Lens for one symbol.

Different investment styles read the same market facts differently. This endpoint returns deterministic,
grounded persona-style reads without buy/sell calls or targets.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from api.deps import CurrentLocale, CurrentTenant, DbSession, enforce_market_feature
from api.routers.market import load_freshest_quotes
from bulls.analytics import InvestorLensResponse, build_investor_lens
from bulls.core.markets import get_market_profile
from bulls.core.models import (
    Announcement,
    AnnualFinancial,
    CompanyProfile,
    DividendRecord,
    InstitutionalHoldingSummary,
    SecFiling,
    Symbol,
    TickerAnalytics,
)

router = APIRouter(tags=["investor-lens"])


@router.get("/symbols/{code}/investor-lens")
async def get_investor_lens(
    code: str, tenant: CurrentTenant, session: DbSession, locale: CurrentLocale
) -> InvestorLensResponse:
    enforce_market_feature(tenant, "interpreted_analytics")
    code = code.upper()
    sym = await session.get(Symbol, (tenant.market, code))
    if sym is None or not sym.is_retail_ready:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")

    ta = await session.get(TickerAnalytics, (tenant.market, code))
    if ta is None:
        raise HTTPException(status_code=404, detail=f"No analytics for {code!r} yet")

    quote = (
        await load_freshest_quotes(
            session,
            tenant.market,
            [code],
            get_market_profile(tenant.market).tz,
        )
    ).get(code)
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

    # Recent material announcements (last 90 days) — so the lens can say "2 recent (dividend)" or
    # "none", instead of telling the user to go hunt the news themselves. 90d (a quarter) matches the
    # reporting cadence: a 30d window missed genuinely recent earnings/dividends and read "none".
    since = ta.as_of_date - dt.timedelta(days=90)
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
    # Attach a direction cue to the most-recent item so the lens shows the earnings *impact*
    # (up/down), not just that news happened. Arrow only, no colour — it states the fact without
    # implying a buy/sell call. Board meetings / dividends carry no direction, so no arrow.
    recent_news_label: str | None = None
    if news:
        top = news[0]
        det = top.details or {}
        arrow = ""
        if top.category == "earnings":
            trend = det.get("eps_trend")
            if trend in {"up", "to_profit", "loss_narrowed"}:
                arrow = " ▲"
            elif trend in {"down", "to_loss", "loss_widened"}:
                arrow = " ▼"
        elif top.category == "rating":
            if det.get("action") == "upgrade":
                arrow = " ▲"
            elif det.get("action") == "downgrade":
                arrow = " ▼"
        recent_news_label = f"{top.category}{arrow}"

    # US official evidence lives in normalized EDGAR filings, not the DSE announcement table.
    # Fold it into the same 90-day check without pretending every filing is directional news.
    if get_market_profile(tenant.market).features.sec_filings:
        filings = list(
            await session.scalars(
                select(SecFiling)
                .where(
                    SecFiling.market == tenant.market,
                    SecFiling.code == code,
                    SecFiling.filing_date >= since,
                )
                .order_by(SecFiling.filing_date.desc())
            )
        )
        if filings:
            latest_filing = filings[0]
            news.extend(filings)
            recent_news_label = f"{latest_filing.form} · {latest_filing.category.replace('_', ' ')}"

    # Dividend track record (last few years) — so the Dividend lens shows consistency + latest
    # cash/bonus split instead of "check payout history / bonus vs cash".
    divs = list(
        await session.scalars(
            select(DividendRecord)
            .where(DividendRecord.market == tenant.market, DividendRecord.code == code)
            .order_by(DividendRecord.year.desc())
            .limit(6)
        )
    )
    div_total_years = len(divs)
    div_paid_years = sum(1 for dv in divs if (dv.cash_pct or 0) > 0 or (dv.cash_per_share or 0) > 0)
    latest_cash_pct = divs[0].cash_pct if divs else None
    latest_cash_per_share = divs[0].cash_per_share if divs else None
    latest_dividend_year = divs[0].year if divs else None
    latest_bonus_pct = divs[0].bonus_pct if divs else None

    holding_summary = None
    if get_market_profile(tenant.market).features.institutional_holdings:
        holding_summary = await session.scalar(
            select(InstitutionalHoldingSummary)
            .where(
                InstitutionalHoldingSummary.market == tenant.market,
                InstitutionalHoldingSummary.code == code,
            )
            .order_by(InstitutionalHoldingSummary.report_date.desc())
            .limit(1)
        )

    # Multi-year EPS (oldest -> newest) for the Buffett 5-year earnings trend check.
    fins = list(
        await session.scalars(
            select(AnnualFinancial)
            .where(AnnualFinancial.market == tenant.market, AnnualFinancial.code == code)
            .order_by(AnnualFinancial.fiscal_year.asc())
            .limit(6)
        )
    )
    eps_history = [f.eps for f in fins if f.eps is not None]

    # Next board meeting (the next earnings/dividend decision) — DSE announces it ~a week ahead and
    # carries the date in the announcement details, so we can SHOW it instead of "check disclosure date".
    next_meeting_date: str | None = None
    next_meeting_period: str | None = None
    today_iso = dt.date.today().isoformat()
    bms = await session.scalars(
        select(Announcement)
        .where(
            Announcement.market == tenant.market,
            Announcement.code == code,
            Announcement.category == "board_meeting",
        )
        .order_by(Announcement.published_at.desc())
        .limit(6)
    )
    for a in bms:
        md = (a.details or {}).get("meeting_date")
        if (
            isinstance(md, str)
            and md >= today_iso
            and (next_meeting_date is None or md < next_meeting_date)
        ):
            next_meeting_date, next_meeting_period = md, (a.details or {}).get("period")

    return build_investor_lens(
        code=code,
        as_of_date=str(ta.as_of_date),
        locale=locale,
        market=tenant.market,
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
        recent_news_label=recent_news_label,
        div_paid_years=div_paid_years,
        div_total_years=div_total_years,
        latest_cash_pct=latest_cash_pct,
        latest_cash_per_share=latest_cash_per_share,
        latest_dividend_year=latest_dividend_year,
        institutional_reported_change_pct=(
            holding_summary.net_change_pct if holding_summary else None
        ),
        institutional_report_date=(str(holding_summary.report_date) if holding_summary else None),
        latest_bonus_pct=latest_bonus_pct,
        eps_history=eps_history,
        next_meeting_date=next_meeting_date,
        next_meeting_period=next_meeting_period,
    )
