"""Portfolio — manual holdings, valued at read time against the latest (delayed) quotes.

The math lives in compute_portfolio() as a pure function so it unit-tests without a database.
We never connect to a broker account; every row is something the user typed in themselves.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from api.deps import CurrentLocale, CurrentTenant, CurrentUser, DbSession
from bulls.core.models import (
    AlertEvent,
    DailyBar,
    PortfolioHolding,
    PortfolioSnapshot,
    PriceAlert,
    QuoteSnapshot,
    Symbol,
)
from bulls.market_data.calendar import market_close_on, market_timezone

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

MAX_HOLDINGS_PER_USER = 100


def _pick(i18n: dict | None, locale: str) -> str | None:
    if not i18n:
        return None
    return i18n.get(locale) or i18n.get("en") or next(iter(i18n.values()), None)


class HoldingIn(BaseModel):
    code: str
    quantity: int = Field(gt=0)
    avg_cost: float = Field(gt=0)


class HoldingOut(BaseModel):
    code: str
    name: str | None
    quantity: int
    avg_cost: float
    ltp: float | None
    as_of: dt.datetime | None
    value: float | None
    day_change_pct: float | None
    pnl: float | None
    pnl_pct: float | None
    # "What's happening" — not just P&L. The latest inbox alert for this code (already fanned
    # out to holders, so this is a read, not a new computation) + whether a price alert is set.
    latest_alert_title: str | None = None
    latest_alert_at: dt.datetime | None = None
    has_price_alert: bool = False


class PortfolioOut(BaseModel):
    holdings: list[HoldingOut]
    total_value: float | None
    total_cost: float
    day_pnl: float | None
    day_pnl_pct: float | None
    total_pnl: float | None
    total_pnl_pct: float | None


@dataclass
class QuoteView:
    """The slice of a quote the valuation needs — makes compute_portfolio() DB-free."""

    ltp: float
    change: float  # absolute ৳ move today
    change_pct: float
    as_of: dt.datetime | None


@dataclass
class AlertView:
    """The slice of a user's latest alert for one code that the portfolio view needs."""

    title: str | None
    created_at: dt.datetime


def compute_portfolio(
    holdings: list[PortfolioHolding],
    quotes: dict[str, QuoteView],
    names: dict[str, str | None] | None = None,
    latest_alerts: dict[str, AlertView] | None = None,
    alert_codes: set[str] | None = None,
) -> PortfolioOut:
    latest_alerts = latest_alerts or {}
    alert_codes = alert_codes or set()
    out: list[HoldingOut] = []
    total_value = 0.0
    total_cost = 0.0
    day_pnl = 0.0
    priced_cost = 0.0  # cost basis of the rows we could actually value
    any_priced = False
    for h in holdings:
        cost = h.quantity * h.avg_cost
        total_cost += cost
        la = latest_alerts.get(h.code)
        q = quotes.get(h.code)
        if q is None:
            out.append(
                HoldingOut(
                    code=h.code,
                    name=(names or {}).get(h.code),
                    quantity=h.quantity,
                    avg_cost=h.avg_cost,
                    ltp=None,
                    as_of=None,
                    value=None,
                    day_change_pct=None,
                    pnl=None,
                    pnl_pct=None,
                    latest_alert_title=la.title if la else None,
                    latest_alert_at=la.created_at if la else None,
                    has_price_alert=h.code in alert_codes,
                )
            )
            continue
        any_priced = True
        value = h.quantity * q.ltp
        pnl = value - cost
        total_value += value
        day_pnl += h.quantity * q.change
        priced_cost += cost
        out.append(
            HoldingOut(
                code=h.code,
                name=(names or {}).get(h.code),
                quantity=h.quantity,
                avg_cost=h.avg_cost,
                ltp=q.ltp,
                as_of=q.as_of,
                value=round(value, 2),
                day_change_pct=q.change_pct,
                pnl=round(pnl, 2),
                pnl_pct=round(pnl / cost * 100, 2) if cost else None,
                latest_alert_title=la.title if la else None,
                latest_alert_at=la.created_at if la else None,
                has_price_alert=h.code in alert_codes,
            )
        )
    prev_value = total_value - day_pnl
    return PortfolioOut(
        holdings=out,
        total_value=round(total_value, 2) if any_priced else None,
        total_cost=round(total_cost, 2),
        day_pnl=round(day_pnl, 2) if any_priced else None,
        day_pnl_pct=round(day_pnl / prev_value * 100, 2) if any_priced and prev_value else None,
        total_pnl=round(total_value - priced_cost, 2) if any_priced else None,
        total_pnl_pct=(
            round((total_value - priced_cost) / priced_cost * 100, 2)
            if any_priced and priced_cost
            else None
        ),
    )


# A holding's "what's happening" only looks at recent alerts — a 6-month-old note isn't news.
_LATEST_ALERT_WINDOW = dt.timedelta(days=21)


async def load_quote_views(session, market: str, codes: list[str]) -> dict[str, QuoteView]:
    """Load current quotes, falling back to each security's latest adjusted EOD close."""
    quotes: dict[str, QuoteView] = {}
    if not codes:
        return quotes

    for q in await session.scalars(
        select(QuoteSnapshot).where(QuoteSnapshot.market == market, QuoteSnapshot.code.in_(codes))
    ):
        quotes[q.code] = QuoteView(
            ltp=q.ltp, change=q.change, change_pct=q.change_pct, as_of=q.as_of
        )

    missing = [code for code in codes if code not in quotes]
    if not missing:
        return quotes

    effective_close = func.coalesce(DailyBar.adjusted_close, DailyBar.close)
    ranked = (
        select(
            DailyBar.code.label("code"),
            DailyBar.date.label("date"),
            effective_close.label("close"),
            func.lead(effective_close)
            .over(partition_by=DailyBar.code, order_by=DailyBar.date.desc())
            .label("prev_close"),
            func.row_number()
            .over(partition_by=DailyBar.code, order_by=DailyBar.date.desc())
            .label("row_num"),
        )
        .where(DailyBar.market == market, DailyBar.code.in_(missing))
        .subquery()
    )
    for code, date, close, prev_close in await session.execute(
        select(
            ranked.c.code,
            ranked.c.date,
            ranked.c.close,
            ranked.c.prev_close,
        ).where(ranked.c.row_num == 1)
    ):
        change = close - prev_close if prev_close else 0.0
        quotes[code] = QuoteView(
            ltp=close,
            change=change,
            change_pct=(change / prev_close * 100) if prev_close else 0.0,
            as_of=dt.datetime.combine(
                date,
                market_close_on(date, market),
                tzinfo=market_timezone(market),
            ),
        )
    return quotes


@router.get("")
async def get_portfolio(
    user: CurrentUser, tenant: CurrentTenant, session: DbSession, locale: CurrentLocale
) -> PortfolioOut:
    holdings = (
        await session.scalars(
            select(PortfolioHolding)
            .where(PortfolioHolding.user_id == user.id, PortfolioHolding.market == tenant.market)
            .order_by(PortfolioHolding.created_at)
        )
    ).all()
    codes = [h.code for h in holdings]
    quotes: dict[str, QuoteView] = {}
    names: dict[str, str | None] = {}
    latest_alerts: dict[str, AlertView] = {}
    alert_codes: set[str] = set()
    if codes:
        quotes = await load_quote_views(session, tenant.market, codes)
        for code, name in await session.execute(
            select(Symbol.code, Symbol.name_en).where(
                Symbol.market == tenant.market, Symbol.code.in_(codes)
            )
        ):
            names[code] = name
        # Reuses the same alert fan-out already written for the bell inbox (holders are already
        # in its audience) — one row per code, newest first, via Postgres DISTINCT ON.
        since = dt.datetime.now(dt.UTC) - _LATEST_ALERT_WINDOW
        for code, title_i18n, created_at in await session.execute(
            select(AlertEvent.code, AlertEvent.title_i18n, AlertEvent.created_at)
            .where(
                AlertEvent.user_id == user.id,
                AlertEvent.tenant_id == tenant.name,
                AlertEvent.market == tenant.market,
                AlertEvent.code.in_(codes),
                AlertEvent.created_at >= since,
            )
            .distinct(AlertEvent.code)
            .order_by(AlertEvent.code, AlertEvent.created_at.desc())
        ):
            latest_alerts[code] = AlertView(title=_pick(title_i18n, locale), created_at=created_at)
        alert_codes = set(
            await session.scalars(
                select(PriceAlert.code).where(
                    PriceAlert.user_id == user.id,
                    PriceAlert.tenant_id == tenant.name,
                    PriceAlert.market == tenant.market,
                    PriceAlert.code.in_(codes),
                    PriceAlert.triggered_at.is_(None),
                )
            )
        )
    return compute_portfolio(list(holdings), quotes, names, latest_alerts, alert_codes)


class PortfolioHistoryPoint(BaseModel):
    date: str
    total_value: float | None
    total_cost: float


_HISTORY_PERIOD_DAYS: dict[str, int | None] = {
    "1w": 7,
    "1m": 30,
    "3m": 90,
    "6m": 180,
    "1y": 365,
    "all": None,
}


@router.get("/history")
async def portfolio_history(
    user: CurrentUser,
    tenant: CurrentTenant,
    session: DbSession,
    period: str = Query("3m", pattern="^(1w|1m|3m|6m|1y|all)$"),
) -> list[PortfolioHistoryPoint]:
    """Daily total value/cost, from the snapshot table (see ingestion.portfolio_snapshot) — never
    reconstructed from current holdings, so this only shows growth since we started tracking."""
    stmt = select(PortfolioSnapshot).where(
        PortfolioSnapshot.user_id == user.id, PortfolioSnapshot.market == tenant.market
    )
    days = _HISTORY_PERIOD_DAYS[period]
    if days is not None:
        since = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=days)
        stmt = stmt.where(PortfolioSnapshot.date >= since)
    rows = (await session.scalars(stmt.order_by(PortfolioSnapshot.date.asc()))).all()
    return [
        PortfolioHistoryPoint(date=str(r.date), total_value=r.total_value, total_cost=r.total_cost)
        for r in rows
    ]


@router.post("/holdings", status_code=201)
async def upsert_holding(
    body: HoldingIn, user: CurrentUser, tenant: CurrentTenant, session: DbSession
) -> dict[str, str]:
    code = body.code.upper()
    symbol = await session.get(Symbol, (tenant.market, code))
    if symbol is None or not symbol.is_public_research:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")
    existing = await session.get(PortfolioHolding, (user.id, tenant.market, code))
    if existing is not None:
        existing.quantity = body.quantity
        existing.avg_cost = body.avg_cost
        return {"status": "updated", "code": code}
    count = len(
        (
            await session.scalars(
                select(PortfolioHolding.code).where(PortfolioHolding.user_id == user.id)
            )
        ).all()
    )
    if count >= MAX_HOLDINGS_PER_USER:
        raise HTTPException(status_code=429, detail="Too many holdings")
    session.add(
        PortfolioHolding(
            user_id=user.id,
            market=tenant.market,
            code=code,
            quantity=body.quantity,
            avg_cost=body.avg_cost,
        )
    )
    return {"status": "created", "code": code}


@router.delete("/holdings/{code}", status_code=204)
async def delete_holding(
    code: str, user: CurrentUser, tenant: CurrentTenant, session: DbSession
) -> None:
    h = await session.get(PortfolioHolding, (user.id, tenant.market, code.upper()))
    if h is not None:
        await session.delete(h)


class VisibilityIn(BaseModel):
    public: bool


@router.patch("/visibility")
async def set_portfolio_visibility(
    body: VisibilityIn, user: CurrentUser, session: DbSession
) -> dict[str, bool]:
    """Opt in/out of showing holdings on the public profile (/u/{handle}). Off by default —
    this is the only endpoint that can turn it on, and only for the signed-in user's own account."""
    user.portfolio_public = body.public
    await session.flush()
    return {"public": user.portfolio_public}
