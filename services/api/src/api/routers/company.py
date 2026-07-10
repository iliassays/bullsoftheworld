"""Company data for the symbol page — fundamentals, ownership, earnings history.

One read powering three tabs. Descriptive facts only; any field we can't compute is null (the UI
shows "—") — we never guess. Valuation + ownership come from the persisted analytics snapshot, the
rest from the weekly company scrape.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from api.deps import CurrentTenant, DbSession, enforce_market_feature
from bulls.core.models import (
    AnnualFinancial,
    CompanyProfile,
    DividendRecord,
    ShareholdingSnapshot,
    Symbol,
    TickerAnalytics,
)

router = APIRouter(tags=["company"])


class Fundamentals(BaseModel):
    market_cap_mn: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    dividend_yield: float | None = None
    pe_vs_sector: float | None = None
    eps: float | None = None
    nav_per_share: float | None = None
    eps_growth_yoy: float | None = None
    outstanding_shares: int | None = None
    free_float_cap_mn: float | None = None
    face_value: float | None = None
    sector: str | None = None
    credit_rating: str | None = None
    week52_high: float | None = None
    week52_low: float | None = None
    avg_volume_20: float | None = None


class OwnershipPoint(BaseModel):
    """One disclosed shareholding snapshot — for the per-category trend over time."""

    as_of: str
    sponsor: float | None = None
    institute: float | None = None
    foreign: float | None = None
    public: float | None = None


class Ownership(BaseModel):
    sponsor_pct: float | None = None
    institute_pct: float | None = None
    foreign_pct: float | None = None
    public_pct: float | None = None
    institute_delta: float | None = None
    foreign_delta: float | None = None
    as_of: str | None = None
    history: list[OwnershipPoint] = []  # all disclosures, oldest→newest, for the trend view


class EarningsRow(BaseModel):
    fiscal_year: int
    eps: float | None = None
    nav_per_share: float | None = None
    profit_mn: float | None = None


class DividendRow(BaseModel):
    year: int
    cash_pct: float | None = None
    bonus_pct: float | None = None


class CompanyResponse(BaseModel):
    code: str
    fundamentals: Fundamentals
    ownership: Ownership
    earnings: list[EarningsRow]
    dividends: list[DividendRow]


@router.get("/symbols/{code}/company")
async def get_company(code: str, tenant: CurrentTenant, session: DbSession) -> CompanyResponse:
    enforce_market_feature(tenant, "company_fundamentals")
    code = code.upper()
    symbol = await session.get(Symbol, (tenant.market, code))
    if symbol is None or not symbol.is_retail_ready:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")

    ta = await session.get(TickerAnalytics, (tenant.market, code))
    prof = await session.get(CompanyProfile, (tenant.market, code))
    snaps = list(
        await session.scalars(
            select(ShareholdingSnapshot)
            .where(ShareholdingSnapshot.market == tenant.market, ShareholdingSnapshot.code == code)
            .order_by(ShareholdingSnapshot.as_of_date.asc())  # oldest→newest, for the trend
        )
    )
    sh_history = [
        OwnershipPoint(
            as_of=str(s.as_of_date),
            sponsor=s.sponsor_director,
            institute=s.institute,
            foreign=s.foreign_pct,
            public=s.public,
        )
        for s in snaps
    ]
    last_sh = snaps[-1].as_of_date if snaps else None
    earnings = list(
        await session.scalars(
            select(AnnualFinancial)
            .where(AnnualFinancial.market == tenant.market, AnnualFinancial.code == code)
            .order_by(AnnualFinancial.fiscal_year.desc())
        )
    )
    dividends = list(
        await session.scalars(
            select(DividendRecord)
            .where(DividendRecord.market == tenant.market, DividendRecord.code == code)
            .order_by(DividendRecord.year.desc())
        )
    )

    rating = None
    if prof:
        rating = prof.credit_rating_long or prof.credit_rating_short

    return CompanyResponse(
        code=code,
        fundamentals=Fundamentals(
            market_cap_mn=ta.market_cap_mn if ta else None,
            pe_ratio=ta.pe_ratio if ta else None,
            pb_ratio=ta.pb_ratio if ta else None,
            dividend_yield=ta.dividend_yield if ta else None,
            pe_vs_sector=ta.pe_vs_sector if ta else None,
            eps_growth_yoy=ta.eps_growth_yoy if ta else None,
            free_float_cap_mn=ta.free_float_cap_mn if ta else None,
            eps=prof.eps if prof else None,
            nav_per_share=prof.nav_per_share if prof else None,
            outstanding_shares=prof.outstanding_shares if prof else None,
            face_value=prof.face_value if prof else None,
            sector=prof.sector if prof else None,
            credit_rating=rating,
            week52_high=ta.week52_high if ta else None,
            week52_low=ta.week52_low if ta else None,
            avg_volume_20=ta.avg_volume_20 if ta else None,
        ),
        ownership=Ownership(
            sponsor_pct=ta.sponsor_pct if ta else None,
            institute_pct=ta.institute_pct if ta else None,
            foreign_pct=ta.foreign_pct if ta else None,
            public_pct=ta.public_pct if ta else None,
            institute_delta=ta.institute_delta if ta else None,
            foreign_delta=ta.foreign_delta if ta else None,
            as_of=str(last_sh) if last_sh else None,
            history=sh_history,
        ),
        earnings=[
            EarningsRow(
                fiscal_year=e.fiscal_year,
                eps=e.eps,
                nav_per_share=e.nav_per_share,
                profit_mn=e.profit_mn,
            )
            for e in earnings
        ],
        dividends=[
            DividendRow(year=d.year, cash_pct=d.cash_pct, bonus_pct=d.bonus_pct) for d in dividends
        ],
    )
