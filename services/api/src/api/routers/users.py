"""Public member profiles — /u/{handle}: name, joined date, their posts, and (only if the member
has explicitly opted in via PATCH /portfolio/visibility) a read-only view of their holdings.

Portfolio visibility is opt-in and off by default (see User.portfolio_public) — a real holdings
list is sensitive, so nothing here is ever shown for an account that hasn't turned it on.
This mirrors desks.py's shape (same public-profile idea, for a regular member instead of an
official desk account) but never exposes desk-only detail like follower counts or bios.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from api.deps import CurrentTenant, DbSession
from api.routers.portfolio import QuoteView, compute_portfolio
from bulls.core.models import PortfolioHolding, PortfolioSnapshot, Post, QuoteSnapshot, Symbol, User

router = APIRouter(prefix="/users", tags=["users"])


class UserProfileOut(BaseModel):
    handle: str
    name: str
    joined: str  # "Jan 2025"
    posts: int
    portfolio_public: bool


async def _resolve_user(session, tenant, handle: str) -> User:
    u = await session.scalar(
        select(User).where(User.tenant_id == tenant.name, User.handle == handle)
    )
    if u is None:
        raise HTTPException(status_code=404, detail=f"Unknown member {handle!r}")
    return u


@router.get("/{handle}")
async def user_profile(handle: str, tenant: CurrentTenant, session: DbSession) -> UserProfileOut:
    u = await _resolve_user(session, tenant, handle)
    posts = await session.scalar(
        select(func.count(Post.id)).where(
            Post.author_id == u.id, Post.parent_id.is_(None), Post.moderation_status == "published"
        )
    )
    return UserProfileOut(
        handle=u.handle,
        name=u.name,
        joined=u.created_at.strftime("%b %Y"),
        posts=int(posts or 0),
        portfolio_public=u.portfolio_public,
    )


class PublicHoldingOut(BaseModel):
    code: str
    name: str | None
    quantity: int
    avg_cost: float
    ltp: float | None
    value: float | None
    day_change_pct: float | None
    pnl: float | None
    pnl_pct: float | None


class PublicPortfolioOut(BaseModel):
    holdings: list[PublicHoldingOut]
    total_value: float | None
    total_cost: float
    day_pnl: float | None
    day_pnl_pct: float | None
    total_pnl: float | None
    total_pnl_pct: float | None


@router.get("/{handle}/portfolio")
async def user_portfolio(
    handle: str, tenant: CurrentTenant, session: DbSession
) -> PublicPortfolioOut:
    u = await _resolve_user(session, tenant, handle)
    if not u.portfolio_public:
        raise HTTPException(status_code=404, detail="This member's portfolio is private")

    holdings = (
        await session.scalars(
            select(PortfolioHolding).where(
                PortfolioHolding.user_id == u.id, PortfolioHolding.market == tenant.market
            )
        )
    ).all()
    codes = [h.code for h in holdings]
    quotes: dict[str, QuoteView] = {}
    names: dict[str, str | None] = {}
    if codes:
        for q in await session.scalars(
            select(QuoteSnapshot).where(
                QuoteSnapshot.market == tenant.market, QuoteSnapshot.code.in_(codes)
            )
        ):
            quotes[q.code] = QuoteView(
                ltp=q.ltp, change=q.change, change_pct=q.change_pct, as_of=q.as_of
            )
        for code, name in await session.execute(
            select(Symbol.code, Symbol.name_en).where(
                Symbol.market == tenant.market, Symbol.code.in_(codes)
            )
        ):
            names[code] = name

    # Reuse the same tested valuation math as the private view — but only project the fields
    # that are safe to show someone else: never the viewer-specific alert/notification state
    # compute_portfolio() also computes (those default to empty here since we pass no alerts).
    full = compute_portfolio(list(holdings), quotes, names)
    return PublicPortfolioOut(
        holdings=[
            PublicHoldingOut(
                code=h.code,
                name=h.name,
                quantity=h.quantity,
                avg_cost=h.avg_cost,
                ltp=h.ltp,
                value=h.value,
                day_change_pct=h.day_change_pct,
                pnl=h.pnl,
                pnl_pct=h.pnl_pct,
            )
            for h in full.holdings
        ],
        total_value=full.total_value,
        total_cost=full.total_cost,
        day_pnl=full.day_pnl,
        day_pnl_pct=full.day_pnl_pct,
        total_pnl=full.total_pnl,
        total_pnl_pct=full.total_pnl_pct,
    )


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


@router.get("/{handle}/portfolio/history")
async def user_portfolio_history(
    handle: str,
    tenant: CurrentTenant,
    session: DbSession,
    period: str = Query("3m", pattern="^(1w|1m|3m|6m|1y|all)$"),
) -> list[PortfolioHistoryPoint]:
    u = await _resolve_user(session, tenant, handle)
    if not u.portfolio_public:
        raise HTTPException(status_code=404, detail="This member's portfolio is private")

    stmt = select(PortfolioSnapshot).where(
        PortfolioSnapshot.user_id == u.id, PortfolioSnapshot.market == tenant.market
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
