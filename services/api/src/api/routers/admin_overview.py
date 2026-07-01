"""Admin portal — a system-wide overview per tenant (admin-token gated).

Unlike the rest of the API, these endpoints don't resolve the tenant from the request host: the admin
picks a tenant from a combo, so `tenant` is an explicit query param validated against the registry.
Read-only aggregates across content, moderation, and data-pipeline health — the "overall picture".
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import desc, func, select

from api.deps import DbSession, require_admin
from bulls.core.models import (
    Cashtag,
    ModerationEvent,
    Post,
    PostReaction,
    QuoteSnapshot,
    Symbol,
    TickerAnalytics,
    User,
)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class TenantOut(BaseModel):
    name: str
    display_name: str
    market: str


@router.get("/tenants")
async def list_tenants(request: Request) -> list[TenantOut]:
    """Every configured tenant — drives the admin tenant selector."""
    reg = request.app.state.tenants
    return [
        TenantOut(name=t.name, display_name=t.display_name, market=t.market) for t in reg.all()
    ]


class RecentEvent(BaseModel):
    post_id: int
    decision: str
    categories: list[str]
    reason_code: str | None
    layer: int
    created_at: dt.datetime


class TopCashtag(BaseModel):
    code: str
    posts: int


class OverviewOut(BaseModel):
    tenant: str
    market: str
    generated_at: dt.datetime
    # content + people
    users: int
    posts_total: int
    posts_today: int
    agent_notes: int
    reactions_7d: int
    # moderation
    moderation: dict[str, int]  # status -> count
    review_pending: int  # pending + held (actionable backlog)
    flagged_24h: int  # decisions that held/blocked in the last 24h
    recent_events: list[RecentEvent]
    top_cashtags: list[TopCashtag]
    # data pipeline health
    last_eod_date: dt.date | None
    latest_quote_as_of: dt.datetime | None
    symbols_active: int
    symbols_hidden: int


async def _count(session, stmt) -> int:
    return (await session.scalar(stmt)) or 0


@router.get("/overview")
async def overview(
    request: Request,
    session: DbSession,
    tenant: str = Query(..., description="Tenant name (from /admin/tenants)"),
) -> OverviewOut:
    t = request.app.state.tenants.get(tenant)
    if t is None:
        raise HTTPException(status_code=404, detail=f"Unknown tenant: {tenant}")
    name, market = t.name, t.market
    now = dt.datetime.now(dt.UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    since_24h = now - dt.timedelta(hours=24)
    since_7d = now - dt.timedelta(days=7)

    users = await _count(session, select(func.count()).select_from(User).where(User.tenant_id == name))

    # posts by moderation_status
    moderation: dict[str, int] = {"published": 0, "pending": 0, "held": 0, "blocked": 0}
    for status, n in (
        await session.execute(
            select(Post.moderation_status, func.count())
            .where(Post.tenant_id == name)
            .group_by(Post.moderation_status)
        )
    ).all():
        moderation[status] = n
    posts_total = sum(moderation.values())

    posts_today = await _count(
        session,
        select(func.count())
        .select_from(Post)
        .where(
            Post.tenant_id == name,
            Post.moderation_status == "published",
            Post.created_at >= day_start,
        ),
    )
    agent_notes = await _count(
        session, select(func.count()).select_from(Post).where(Post.tenant_id == name, Post.kind == "note")
    )
    reactions_7d = await _count(
        session,
        select(func.count())
        .select_from(PostReaction)
        .join(Post, Post.id == PostReaction.post_id)
        .where(Post.tenant_id == name, PostReaction.created_at >= since_7d),
    )

    flagged_24h = await _count(
        session,
        select(func.count())
        .select_from(ModerationEvent)
        .where(
            ModerationEvent.tenant_id == name,
            ModerationEvent.decision.in_(("hold", "block")),
            ModerationEvent.created_at >= since_24h,
        ),
    )

    recent_events = [
        RecentEvent(
            post_id=ev.post_id,
            decision=ev.decision,
            categories=list(ev.categories or []),
            reason_code=ev.reason_code,
            layer=ev.layer,
            created_at=ev.created_at,
        )
        for ev in await session.scalars(
            select(ModerationEvent)
            .where(ModerationEvent.tenant_id == name, ModerationEvent.decision.in_(("hold", "block")))
            .order_by(desc(ModerationEvent.created_at))
            .limit(10)
        )
    ]

    top_cashtags = [
        TopCashtag(code=code, posts=n)
        for code, n in (
            await session.execute(
                select(Cashtag.code, func.count(func.distinct(Post.id)))
                .join(Post, Post.id == Cashtag.post_id)
                .where(
                    Post.tenant_id == name,
                    Post.moderation_status == "published",
                    Post.created_at >= since_7d,
                )
                .group_by(Cashtag.code)
                .order_by(desc(func.count(func.distinct(Post.id))))
                .limit(8)
            )
        ).all()
    ]

    last_eod_date = await session.scalar(
        select(func.max(TickerAnalytics.as_of_date)).where(TickerAnalytics.market == market)
    )
    latest_quote_as_of = await session.scalar(
        select(func.max(QuoteSnapshot.as_of)).where(QuoteSnapshot.market == market)
    )
    symbols_active = await _count(
        session,
        select(func.count()).select_from(Symbol).where(Symbol.market == market, Symbol.is_active.is_(True)),
    )
    symbols_hidden = await _count(
        session,
        select(func.count()).select_from(Symbol).where(Symbol.market == market, Symbol.is_hidden.is_(True)),
    )

    return OverviewOut(
        tenant=name,
        market=market,
        generated_at=now,
        users=users,
        posts_total=posts_total,
        posts_today=posts_today,
        agent_notes=agent_notes,
        reactions_7d=reactions_7d,
        moderation=moderation,
        review_pending=moderation["pending"] + moderation["held"],
        flagged_24h=flagged_24h,
        recent_events=recent_events,
        top_cashtags=top_cashtags,
        last_eod_date=last_eod_date,
        latest_quote_as_of=latest_quote_as_of,
        symbols_active=symbols_active,
        symbols_hidden=symbols_hidden,
    )
