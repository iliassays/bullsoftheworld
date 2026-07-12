"""Company data for the symbol page — fundamentals, ownership, earnings history.

One read powering three tabs. Descriptive facts only; any field we can't compute is null (the UI
shows "—") — we never guess. Valuation comes from the analytics snapshot; ownership is reconciled
from validated disclosures so current values, deltas, and history always share one source.
"""

from __future__ import annotations

import itertools
import math

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.deps import CurrentTenant, DbSession, enforce_market_feature
from bulls.core.models import (
    AnnualFinancial,
    CompanyProfile,
    DividendRecord,
    SecFinancialFact,
    ShareholdingSnapshot,
    Symbol,
    TickerAnalytics,
)

router = APIRouter(tags=["company"])


class Fundamentals(BaseModel):
    valuation_as_of: str | None = None
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
    govt: float | None = None
    institute: float | None = None
    foreign: float | None = None
    public: float | None = None


class Ownership(BaseModel):
    sponsor_pct: float | None = None
    govt_pct: float | None = None
    institute_pct: float | None = None
    foreign_pct: float | None = None
    public_pct: float | None = None
    sponsor_delta: float | None = None
    govt_delta: float | None = None
    institute_delta: float | None = None
    foreign_delta: float | None = None
    public_delta: float | None = None
    composition_total: float | None = None
    as_of: str | None = None
    history: list[OwnershipPoint] = Field(default_factory=list)


class EarningsRow(BaseModel):
    fiscal_year: int
    eps: float | None = None
    nav_per_share: float | None = None
    profit_mn: float | None = None


class DividendRow(BaseModel):
    year: int
    cash_pct: float | None = None
    cash_per_share: float | None = None
    bonus_pct: float | None = None


class QuarterlyFinancialRow(BaseModel):
    period_end: str
    revenue_mn: float | None = None
    net_income_mn: float | None = None
    eps: float | None = None
    source_url: str | None = None


class FinancialHealth(BaseModel):
    as_of: str | None = None
    revenue_ttm_mn: float | None = None
    net_income_ttm_mn: float | None = None
    profit_margin_pct: float | None = None
    operating_cash_flow_ttm_mn: float | None = None
    capital_expenditure_ttm_mn: float | None = None
    free_cash_flow_ttm_mn: float | None = None
    assets_mn: float | None = None
    liabilities_mn: float | None = None
    equity_mn: float | None = None
    cash_mn: float | None = None
    debt_mn: float | None = None
    current_ratio: float | None = None
    debt_to_equity: float | None = None
    source_url: str | None = None


class CompanyResponse(BaseModel):
    code: str
    fundamentals: Fundamentals
    ownership: Ownership
    earnings: list[EarningsRow]
    dividends: list[DividendRow]
    quarters: list[QuarterlyFinancialRow] = Field(default_factory=list)
    financial_health: FinancialHealth = Field(default_factory=FinancialHealth)


def _facts_by_metric(rows: list[SecFinancialFact], metric: str, period_type: str | None = None):
    return [
        row
        for row in rows
        if row.metric == metric and (period_type is None or row.period_type == period_type)
    ]


def _latest_fact(
    rows: list[SecFinancialFact], metric: str, period_type: str | None = None
) -> SecFinancialFact | None:
    candidates = _facts_by_metric(rows, metric, period_type)
    return max(candidates, key=lambda row: (row.period_end, row.filed_at)) if candidates else None


def _ttm(rows: list[SecFinancialFact], metric: str) -> tuple[float | None, str | None]:
    quarters = sorted(
        _facts_by_metric(rows, metric, "quarter"),
        key=lambda row: (row.period_end, row.filed_at),
        reverse=True,
    )
    latest_four = quarters[:4]
    if len(latest_four) == 4 and all(
        60 <= (newer.period_end - older.period_end).days <= 130
        for newer, older in itertools.pairwise(latest_four)
    ):
        return sum(row.value for row in latest_four), latest_four[0].source_url
    annual = _latest_fact(rows, metric, "annual")
    if annual is None:
        return None, None
    newer = [row for row in quarters if row.period_end > annual.period_end]
    if not newer:
        return annual.value, annual.source_url
    replacements: list[tuple[SecFinancialFact, SecFinancialFact]] = []
    for current in newer:
        prior = next(
            (
                candidate
                for candidate in quarters
                if 345 <= (current.period_end - candidate.period_end).days <= 385
            ),
            None,
        )
        if prior is None:
            return annual.value, annual.source_url
        replacements.append((current, prior))
    value = annual.value + sum(current.value - prior.value for current, prior in replacements)
    return value, newer[0].source_url


def _financial_health(rows: list[SecFinancialFact]) -> FinancialHealth:
    revenue, revenue_url = _ttm(rows, "revenue")
    income, income_url = _ttm(rows, "net_income")
    operating_cf, cashflow_url = _ttm(rows, "operating_cash_flow")
    capex, capex_url = _ttm(rows, "capital_expenditure")
    assets = _latest_fact(rows, "assets", "instant")
    liabilities = _latest_fact(rows, "liabilities", "instant")
    equity = _latest_fact(rows, "equity", "instant")
    cash = _latest_fact(rows, "cash", "instant")
    current_assets = _latest_fact(rows, "current_assets", "instant")
    current_liabilities = _latest_fact(rows, "current_liabilities", "instant")
    debt_current = _latest_fact(rows, "debt_current", "instant")
    debt_noncurrent = _latest_fact(rows, "debt_noncurrent", "instant")
    debt_total = _latest_fact(rows, "debt_total", "instant")
    debt = (
        debt_total.value
        if debt_total is not None
        else sum(fact.value for fact in (debt_current, debt_noncurrent) if fact is not None)
    )
    latest_instant = max(
        (fact for fact in (assets, liabilities, equity, cash) if fact is not None),
        key=lambda fact: fact.period_end,
        default=None,
    )
    return FinancialHealth(
        as_of=str(latest_instant.period_end) if latest_instant else None,
        revenue_ttm_mn=revenue / 1e6 if revenue is not None else None,
        net_income_ttm_mn=income / 1e6 if income is not None else None,
        profit_margin_pct=(income / revenue * 100 if income is not None and revenue else None),
        operating_cash_flow_ttm_mn=operating_cf / 1e6 if operating_cf is not None else None,
        capital_expenditure_ttm_mn=capex / 1e6 if capex is not None else None,
        free_cash_flow_ttm_mn=(
            (operating_cf - capex) / 1e6 if operating_cf is not None and capex is not None else None
        ),
        assets_mn=assets.value / 1e6 if assets else None,
        liabilities_mn=liabilities.value / 1e6 if liabilities else None,
        equity_mn=equity.value / 1e6 if equity else None,
        cash_mn=cash.value / 1e6 if cash else None,
        debt_mn=debt / 1e6 if debt_total or debt_current or debt_noncurrent else None,
        current_ratio=(
            current_assets.value / current_liabilities.value
            if current_assets and current_liabilities and current_liabilities.value
            else None
        ),
        debt_to_equity=(debt / equity.value if equity and equity.value else None),
        source_url=revenue_url or income_url or cashflow_url or capex_url,
    )


def _quarter_rows(rows: list[SecFinancialFact]) -> list[QuarterlyFinancialRow]:
    by_period: dict[str, dict[str, SecFinancialFact]] = {}
    for metric in ("revenue", "net_income", "eps_diluted", "eps_basic"):
        for fact in _facts_by_metric(rows, metric, "quarter"):
            by_period.setdefault(str(fact.period_end), {}).setdefault(metric, fact)
    out = []
    for period, metrics in sorted(by_period.items(), reverse=True)[:8]:
        revenue = metrics.get("revenue")
        income = metrics.get("net_income")
        eps = metrics.get("eps_diluted") or metrics.get("eps_basic")
        source = revenue or income or eps
        out.append(
            QuarterlyFinancialRow(
                period_end=period,
                revenue_mn=revenue.value / 1e6 if revenue else None,
                net_income_mn=income.value / 1e6 if income else None,
                eps=eps.value if eps else None,
                source_url=source.source_url if source else None,
            )
        )
    return out


def _valid_shareholding_snapshot(snapshot: ShareholdingSnapshot) -> bool:
    """Reject incomplete or impossible disclosures before they reach the response."""

    required = (
        snapshot.sponsor_director,
        snapshot.institute,
        snapshot.foreign_pct,
        snapshot.public,
    )
    if any(value is None or not math.isfinite(value) for value in required):
        return False
    values = (*required, snapshot.govt if snapshot.govt is not None else 0.0)
    if any(value < 0 or value > 100 for value in values):
        return False
    return 99 <= sum(values) <= 101


def _ownership_from_snapshots(snapshots: list[ShareholdingSnapshot]) -> Ownership:
    """Build one internally consistent ownership view from validated disclosures only."""

    valid = sorted(
        (snapshot for snapshot in snapshots if _valid_shareholding_snapshot(snapshot)),
        key=lambda snapshot: snapshot.as_of_date,
    )
    if not valid:
        return Ownership()

    latest = valid[-1]
    previous = valid[-2] if len(valid) > 1 else None

    def value(snapshot: ShareholdingSnapshot, field: str) -> float:
        raw = getattr(snapshot, field)
        return float(raw if raw is not None else 0.0)

    def delta(field: str) -> float | None:
        if previous is None:
            return None
        return round(value(latest, field) - value(previous, field), 4)

    history = [
        OwnershipPoint(
            as_of=str(snapshot.as_of_date),
            sponsor=value(snapshot, "sponsor_director"),
            govt=value(snapshot, "govt"),
            institute=value(snapshot, "institute"),
            foreign=value(snapshot, "foreign_pct"),
            public=value(snapshot, "public"),
        )
        for snapshot in valid
    ]
    composition_total = sum(
        value(latest, field)
        for field in ("sponsor_director", "govt", "institute", "foreign_pct", "public")
    )
    return Ownership(
        sponsor_pct=value(latest, "sponsor_director"),
        govt_pct=value(latest, "govt"),
        institute_pct=value(latest, "institute"),
        foreign_pct=value(latest, "foreign_pct"),
        public_pct=value(latest, "public"),
        sponsor_delta=delta("sponsor_director"),
        govt_delta=delta("govt"),
        institute_delta=delta("institute"),
        foreign_delta=delta("foreign_pct"),
        public_delta=delta("public"),
        composition_total=round(composition_total, 4),
        as_of=str(latest.as_of_date),
        history=history,
    )


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
    ownership = _ownership_from_snapshots(snaps)
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
    sec_facts = list(
        await session.scalars(
            select(SecFinancialFact)
            .where(SecFinancialFact.market == tenant.market, SecFinancialFact.code == code)
            .order_by(SecFinancialFact.period_end.desc(), SecFinancialFact.filed_at.desc())
        )
    )

    rating = None
    if prof:
        rating = prof.credit_rating_long or prof.credit_rating_short

    return CompanyResponse(
        code=code,
        fundamentals=Fundamentals(
            valuation_as_of=str(ta.as_of_date) if ta else None,
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
        ownership=ownership,
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
            DividendRow(
                year=d.year,
                cash_pct=d.cash_pct,
                cash_per_share=d.cash_per_share,
                bonus_pct=d.bonus_pct,
            )
            for d in dividends
        ],
        quarters=_quarter_rows(sec_facts),
        financial_health=_financial_health(sec_facts),
    )
