"""Official filing and institutional-holdings evidence for markets that expose those capabilities."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from api.deps import CurrentTenant, DbSession, enforce_market_feature
from bulls.core.models import (
    DailyBar,
    InstitutionalHoldingSummary,
    InstitutionalPosition,
    SecFiling,
    Symbol,
)

router = APIRouter(tags=["regulatory"])


class FilingOut(BaseModel):
    accession_number: str
    form: str
    category: str
    filing_date: str
    report_date: str | None
    title: str
    items: str | None
    url: str


class FilingCalendarItem(BaseModel):
    code: str
    form: str
    category: str
    filing_date: str
    report_date: str | None
    title: str
    url: str


class InstitutionPositionOut(BaseModel):
    manager_cik: int
    manager_name: str
    shares: int
    value_usd: float
    prior_shares: int | None
    share_change: int | None
    change_pct: float | None
    change_type: str
    filing_date: str
    url: str


class HoldingPeriodOut(BaseModel):
    report_date: str
    prior_report_date: str | None
    public_by: str
    managers_count: int
    total_shares: int
    total_value_usd: float
    net_share_change: int | None
    net_change_pct: float | None
    new_positions: int
    increased_positions: int
    reduced_positions: int
    exited_positions: int
    unchanged_positions: int
    close_on_public_date: float | None = None
    latest_close: float | None = None
    return_since_public_pct: float | None = None
    return_30_sessions_pct: float | None = None
    source_url: str


class InstitutionalActivityOut(BaseModel):
    code: str
    periods: list[HoldingPeriodOut]
    top_positions: list[InstitutionPositionOut]
    top_new: list[InstitutionPositionOut]
    top_increases: list[InstitutionPositionOut]
    top_reductions: list[InstitutionPositionOut]
    top_exits: list[InstitutionPositionOut]
    disclosure_note: str
    limitations: list[str]


def _filing_title(filing: SecFiling) -> str:
    label = filing.category.replace("_", " ").title()
    description = (filing.description or "").strip()
    return f"{label}: {description}" if description else f"{label} ({filing.form})"


@router.get("/symbols/{code}/filings")
async def symbol_filings(
    code: str,
    tenant: CurrentTenant,
    session: DbSession,
    limit: int = Query(40, ge=1, le=100),
) -> list[FilingOut]:
    enforce_market_feature(tenant, "sec_filings")
    code = code.upper()
    symbol = await session.get(Symbol, (tenant.market, code))
    if symbol is None or not symbol.is_retail_ready:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")
    filings = list(
        await session.scalars(
            select(SecFiling)
            .where(SecFiling.market == tenant.market, SecFiling.code == code)
            .order_by(SecFiling.filing_date.desc(), SecFiling.accepted_at.desc())
            .limit(limit)
        )
    )
    return [
        FilingOut(
            accession_number=row.accession_number,
            form=row.form,
            category=row.category,
            filing_date=str(row.filing_date),
            report_date=str(row.report_date) if row.report_date else None,
            title=_filing_title(row),
            items=row.items,
            url=row.filing_url,
        )
        for row in filings
    ]


@router.get("/market/filing-calendar")
async def filing_calendar(
    tenant: CurrentTenant,
    session: DbSession,
    days: int = Query(30, ge=1, le=180),
    limit: int = Query(100, ge=1, le=300),
) -> list[FilingCalendarItem]:
    enforce_market_feature(tenant, "sec_filings")
    since = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=days)
    rows = list(
        await session.scalars(
            select(SecFiling)
            .where(
                SecFiling.market == tenant.market,
                SecFiling.filing_date >= since,
                SecFiling.code.in_(
                    select(Symbol.code).where(
                        Symbol.market == tenant.market,
                        Symbol.is_active.is_(True),
                        Symbol.is_hidden.is_(False),
                        Symbol.data_status == "ready",
                    )
                ),
            )
            .order_by(SecFiling.filing_date.desc(), SecFiling.accepted_at.desc())
            .limit(limit)
        )
    )
    return [
        FilingCalendarItem(
            code=row.code,
            form=row.form,
            category=row.category,
            filing_date=str(row.filing_date),
            report_date=str(row.report_date) if row.report_date else None,
            title=_filing_title(row),
            url=row.filing_url,
        )
        for row in rows
    ]


async def _price_context(
    session, market: str, code: str, summaries: list[InstitutionalHoldingSummary]
) -> dict[dt.date, tuple[float | None, float | None, float | None]]:
    if not summaries:
        return {}
    bars = list(
        await session.scalars(
            select(DailyBar)
            .where(
                DailyBar.market == market,
                DailyBar.code == code,
                DailyBar.date
                >= min(row.latest_filing_date for row in summaries) - dt.timedelta(days=7),
            )
            .order_by(DailyBar.date)
        )
    )
    latest = (bars[-1].adjusted_close or bars[-1].close) if bars else None
    out: dict[dt.date, tuple[float | None, float | None, float | None]] = {}
    for summary in summaries:
        after = [bar for bar in bars if bar.date >= summary.latest_filing_date]
        public_close = (after[0].adjusted_close or after[0].close) if after else None
        close_30 = (after[29].adjusted_close or after[29].close) if len(after) >= 30 else None
        return_since = (
            (latest / public_close - 1) * 100
            if latest and public_close and public_close > 0
            else None
        )
        return_30 = (
            (close_30 / public_close - 1) * 100
            if close_30 and public_close and public_close > 0
            else None
        )
        out[summary.report_date] = (public_close, return_since, return_30)
    return out


def _position_out(row: InstitutionalPosition) -> InstitutionPositionOut:
    return InstitutionPositionOut(
        manager_cik=row.manager_cik,
        manager_name=row.manager_name,
        shares=row.shares,
        value_usd=row.value_usd,
        prior_shares=row.prior_shares,
        share_change=row.share_change,
        change_pct=row.change_pct,
        change_type=row.change_type,
        filing_date=str(row.filing_date),
        url=row.source_url,
    )


@router.get("/symbols/{code}/institutional-holdings")
async def institutional_holdings(
    code: str, tenant: CurrentTenant, session: DbSession
) -> InstitutionalActivityOut:
    enforce_market_feature(tenant, "institutional_holdings")
    code = code.upper()
    symbol = await session.get(Symbol, (tenant.market, code))
    if symbol is None or not symbol.is_retail_ready:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")
    summaries = list(
        await session.scalars(
            select(InstitutionalHoldingSummary)
            .where(
                InstitutionalHoldingSummary.market == tenant.market,
                InstitutionalHoldingSummary.code == code,
            )
            .order_by(InstitutionalHoldingSummary.report_date.desc())
            .limit(8)
        )
    )
    if not summaries:
        return InstitutionalActivityOut(
            code=code,
            periods=[],
            top_positions=[],
            top_new=[],
            top_increases=[],
            top_reductions=[],
            top_exits=[],
            disclosure_note="No confidently mapped Form 13F history is available for this security yet.",
            limitations=["Unresolved CUSIPs are excluded instead of guessed."],
        )
    latest_period = summaries[0].report_date
    positions = list(
        await session.scalars(
            select(InstitutionalPosition)
            .where(
                InstitutionalPosition.market == tenant.market,
                InstitutionalPosition.code == code,
                InstitutionalPosition.report_date == latest_period,
            )
            .order_by(InstitutionalPosition.value_rank)
        )
    )
    grouped: dict[str, list[InstitutionalPosition]] = defaultdict(list)
    for row in positions:
        grouped[row.change_type].append(row)
    prices = await _price_context(session, tenant.market, code, summaries)
    latest_bar = await session.scalar(
        select(DailyBar)
        .where(DailyBar.market == tenant.market, DailyBar.code == code)
        .order_by(DailyBar.date.desc())
        .limit(1)
    )
    latest_close = (latest_bar.adjusted_close or latest_bar.close) if latest_bar else None
    period_rows = []
    for row in summaries:
        public_close, return_since, return_30 = prices.get(row.report_date, (None, None, None))
        period_rows.append(
            HoldingPeriodOut(
                report_date=str(row.report_date),
                prior_report_date=str(row.prior_report_date) if row.prior_report_date else None,
                public_by=str(row.latest_filing_date),
                managers_count=row.managers_count,
                total_shares=row.total_shares,
                total_value_usd=row.total_value_usd,
                net_share_change=row.net_share_change,
                net_change_pct=row.net_change_pct,
                new_positions=row.new_positions,
                increased_positions=row.increased_positions,
                reduced_positions=row.reduced_positions,
                exited_positions=row.exited_positions,
                unchanged_positions=row.unchanged_positions,
                close_on_public_date=public_close,
                latest_close=latest_close,
                return_since_public_pct=round(return_since, 2)
                if return_since is not None
                else None,
                return_30_sessions_pct=round(return_30, 2) if return_30 is not None else None,
                source_url=row.source_url,
            )
        )
    return InstitutionalActivityOut(
        code=code,
        periods=period_rows,
        top_positions=[_position_out(row) for row in positions if row.shares > 0][:20],
        top_new=[_position_out(row) for row in grouped["new"][:12]],
        top_increases=[
            _position_out(row)
            for row in sorted(
                grouped["increased"], key=lambda item: item.share_change or 0, reverse=True
            )[:12]
        ],
        top_reductions=[
            _position_out(row)
            for row in sorted(grouped["reduced"], key=lambda item: item.share_change or 0)[:12]
        ],
        top_exits=[
            _position_out(row)
            for row in sorted(
                grouped["exited"], key=lambda item: item.prior_shares or 0, reverse=True
            )[:12]
        ],
        disclosure_note=(
            "Form 13F reports quarter-end holdings and may be filed up to 45 days later. "
            "Price comparisons start when the filings were public, not when managers traded."
        ),
        limitations=[
            "13F does not disclose exact trade dates or entry prices.",
            "Short positions are not reported; options and unresolved CUSIPs are excluded here.",
            "A manager may rebalance for flows, mandates, taxes, or risk rather than a directional view.",
        ],
    )
