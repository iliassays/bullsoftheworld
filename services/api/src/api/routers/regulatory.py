"""Official filing and institutional-holdings evidence for markets that expose those capabilities."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from api.deps import CurrentTenant, DbSession, enforce_market_feature
from bulls.core.models import (
    DailyBar,
    InstitutionalHoldingSummary,
    InstitutionalPosition,
    SecFiling,
    SecurityIdentifier,
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
    return_60_sessions_pct: float | None = None
    benchmark_return_30_sessions_pct: float | None = None
    benchmark_return_60_sessions_pct: float | None = None
    excess_return_30_sessions_pct: float | None = None
    excess_return_60_sessions_pct: float | None = None
    adding_managers: int
    reducing_managers: int
    net_breadth_pct: float | None
    source_url: str


class HoldingHorizonOut(BaseModel):
    quarters: int
    from_report_date: str
    to_report_date: str
    reported_share_change_pct: float


class ManagerHistoryPointOut(BaseModel):
    report_date: str
    reported_manager_name: str
    shares: int
    value_usd: float
    share_change: int | None
    change_pct: float | None
    change_type: str
    filing_date: str
    url: str


class ManagerHistoryOut(BaseModel):
    manager_cik: int
    manager_name: str
    latest_value_usd: float
    points: list[ManagerHistoryPointOut]


class InstitutionalActivityOut(BaseModel):
    code: str
    periods: list[HoldingPeriodOut]
    horizons: list[HoldingHorizonOut]
    manager_histories: list[ManagerHistoryOut]
    top_positions: list[InstitutionPositionOut]
    top_new: list[InstitutionPositionOut]
    top_increases: list[InstitutionPositionOut]
    top_reductions: list[InstitutionPositionOut]
    top_exits: list[InstitutionPositionOut]
    history_quarters: int
    target_history_quarters: int
    history_status: str
    identifier_count: int
    mapping_confidence: float | None
    mapping_methods: list[str]
    bounded_manager_history: bool
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


@dataclass(frozen=True)
class _PriceContext:
    public_close: float | None
    return_since_public: float | None
    return_30: float | None
    return_60: float | None
    benchmark_return_30: float | None
    benchmark_return_60: float | None


def _bar_close(bar: DailyBar) -> float:
    return bar.adjusted_close or bar.close


def _period_return(bars: list[DailyBar], public_date: dt.date, sessions: int) -> float | None:
    after = [bar for bar in bars if bar.date >= public_date]
    if len(after) < sessions:
        return None
    start = _bar_close(after[0])
    end = _bar_close(after[sessions - 1])
    return (end / start - 1) * 100 if start > 0 else None


async def _price_context(
    session, market: str, code: str, summaries: list[InstitutionalHoldingSummary]
) -> tuple[dict[dt.date, _PriceContext], float | None]:
    if not summaries:
        return {}, None
    bars = list(
        await session.scalars(
            select(DailyBar)
            .where(
                DailyBar.market == market,
                DailyBar.code.in_({code, "SPY"}),
                DailyBar.date
                >= min(row.latest_filing_date for row in summaries) - dt.timedelta(days=7),
            )
            .order_by(DailyBar.code, DailyBar.date)
        )
    )
    by_code: dict[str, list[DailyBar]] = defaultdict(list)
    for bar in bars:
        by_code[bar.code].append(bar)
    symbol_bars = by_code[code]
    benchmark_bars = by_code["SPY"]
    latest = _bar_close(symbol_bars[-1]) if symbol_bars else None
    out: dict[dt.date, _PriceContext] = {}
    for summary in summaries:
        after = [bar for bar in symbol_bars if bar.date >= summary.latest_filing_date]
        public_close = _bar_close(after[0]) if after else None
        return_since = (
            (latest / public_close - 1) * 100
            if latest and public_close and public_close > 0
            else None
        )
        out[summary.report_date] = _PriceContext(
            public_close=public_close,
            return_since_public=return_since,
            return_30=_period_return(symbol_bars, summary.latest_filing_date, 30),
            return_60=_period_return(symbol_bars, summary.latest_filing_date, 60),
            benchmark_return_30=_period_return(
                benchmark_bars, summary.latest_filing_date, 30
            ),
            benchmark_return_60=_period_return(
                benchmark_bars, summary.latest_filing_date, 60
            ),
        )
    return out, latest


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


def _holding_horizons(
    summaries: list[InstitutionalHoldingSummary],
) -> list[HoldingHorizonOut]:
    horizons = []
    for quarters in (2, 4, 8):
        if len(summaries) < quarters:
            continue
        latest = summaries[0]
        baseline = summaries[quarters - 1]
        if baseline.total_shares <= 0:
            continue
        horizons.append(
            HoldingHorizonOut(
                quarters=quarters,
                from_report_date=str(baseline.report_date),
                to_report_date=str(latest.report_date),
                reported_share_change_pct=round(
                    (latest.total_shares / baseline.total_shares - 1) * 100, 2
                ),
            )
        )
    return horizons


async def _manager_histories(
    session,
    market: str,
    code: str,
    latest_positions: list[InstitutionalPosition],
) -> list[ManagerHistoryOut]:
    ranked = [row for row in latest_positions if row.shares > 0][:6]
    movers = sorted(
        latest_positions,
        key=lambda row: abs(row.share_change or 0),
        reverse=True,
    )[:4]
    selected_ciks = list(dict.fromkeys(row.manager_cik for row in [*ranked, *movers]))
    if not selected_ciks:
        return []
    history = list(
        await session.scalars(
            select(InstitutionalPosition)
            .where(
                InstitutionalPosition.market == market,
                InstitutionalPosition.code == code,
                InstitutionalPosition.manager_cik.in_(selected_ciks),
            )
            .order_by(
                InstitutionalPosition.manager_cik,
                InstitutionalPosition.report_date.desc(),
            )
        )
    )
    grouped: dict[int, list[InstitutionalPosition]] = defaultdict(list)
    for row in history:
        grouped[row.manager_cik].append(row)
    latest_by_cik = {row.manager_cik: row for row in latest_positions}
    return [
        ManagerHistoryOut(
            manager_cik=cik,
            manager_name=latest_by_cik[cik].manager_name,
            latest_value_usd=latest_by_cik[cik].value_usd,
            points=[
                ManagerHistoryPointOut(
                    report_date=str(row.report_date),
                    reported_manager_name=row.manager_name,
                    shares=row.shares,
                    value_usd=row.value_usd,
                    share_change=row.share_change,
                    change_pct=row.change_pct,
                    change_type=row.change_type,
                    filing_date=str(row.filing_date),
                    url=row.source_url,
                )
                for row in grouped[cik]
            ],
        )
        for cik in selected_ciks
        if cik in grouped
    ]


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
            horizons=[],
            manager_histories=[],
            top_positions=[],
            top_new=[],
            top_increases=[],
            top_reductions=[],
            top_exits=[],
            history_quarters=0,
            target_history_quarters=8,
            history_status="not_available",
            identifier_count=0,
            mapping_confidence=None,
            mapping_methods=[],
            bounded_manager_history=True,
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
    prices, latest_close = await _price_context(session, tenant.market, code, summaries)
    identifiers = list(
        await session.scalars(
            select(SecurityIdentifier).where(
                SecurityIdentifier.market == tenant.market,
                SecurityIdentifier.code == code,
                SecurityIdentifier.identifier_type == "cusip",
            )
        )
    )
    manager_histories = await _manager_histories(
        session, tenant.market, code, positions
    )
    period_rows = []
    for row in summaries:
        price = prices.get(
            row.report_date,
            _PriceContext(None, None, None, None, None, None),
        )
        adding = row.new_positions + row.increased_positions
        reducing = row.reduced_positions + row.exited_positions
        classified = adding + reducing + row.unchanged_positions
        breadth = (adding - reducing) / classified * 100 if classified else None
        excess_30 = (
            price.return_30 - price.benchmark_return_30
            if price.return_30 is not None and price.benchmark_return_30 is not None
            else None
        )
        excess_60 = (
            price.return_60 - price.benchmark_return_60
            if price.return_60 is not None and price.benchmark_return_60 is not None
            else None
        )
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
                close_on_public_date=price.public_close,
                latest_close=latest_close,
                return_since_public_pct=round(price.return_since_public, 2)
                if price.return_since_public is not None
                else None,
                return_30_sessions_pct=round(price.return_30, 2)
                if price.return_30 is not None
                else None,
                return_60_sessions_pct=round(price.return_60, 2)
                if price.return_60 is not None
                else None,
                benchmark_return_30_sessions_pct=round(price.benchmark_return_30, 2)
                if price.benchmark_return_30 is not None
                else None,
                benchmark_return_60_sessions_pct=round(price.benchmark_return_60, 2)
                if price.benchmark_return_60 is not None
                else None,
                excess_return_30_sessions_pct=round(excess_30, 2)
                if excess_30 is not None
                else None,
                excess_return_60_sessions_pct=round(excess_60, 2)
                if excess_60 is not None
                else None,
                adding_managers=adding,
                reducing_managers=reducing,
                net_breadth_pct=round(breadth, 2) if breadth is not None else None,
                source_url=row.source_url,
            )
        )
    return InstitutionalActivityOut(
        code=code,
        periods=period_rows,
        horizons=_holding_horizons(summaries),
        manager_histories=manager_histories,
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
        history_quarters=len(summaries),
        target_history_quarters=8,
        history_status="full_history" if len(summaries) >= 8 else "building_history",
        identifier_count=len(identifiers),
        mapping_confidence=min((row.confidence for row in identifiers), default=None),
        mapping_methods=sorted({row.match_method for row in identifiers}),
        bounded_manager_history=True,
        disclosure_note=(
            "Form 13F reports quarter-end holdings and may be filed up to 45 days later. "
            "Price comparisons start when the filings were public, not when managers traded."
        ),
        limitations=[
            "13F does not disclose exact trade dates or entry prices.",
            "Short positions are not reported; options and unresolved CUSIPs are excluded here.",
            "Aggregate changes can also reflect changes in the population of reporting managers.",
            "A manager may rebalance for flows, mandates, taxes, or risk rather than a directional view.",
            "Manager timelines include only material retained rows and never merge managers by name.",
        ],
    )
