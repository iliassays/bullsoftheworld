"""Admin portal — a system-wide overview per tenant (admin-token gated).

Unlike the rest of the API, these endpoints don't resolve the tenant from the request host: the admin
picks a tenant from a combo, so `tenant` is an explicit query param validated against the registry.
Read-only aggregates across content, moderation, and data-pipeline health — the "overall picture".
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import Date, cast, desc, distinct, func, select

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
    return [TenantOut(name=t.name, display_name=t.display_name, market=t.market) for t in reg.all()]


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
    # people — split real accounts from the automated desks (both are User rows)
    users_people: int  # is_official = false (humans)
    users_desks: int  # is_official = true (agent desks)
    # posts — split human posts from agent desk-notes
    posts_total: int
    user_posts: int  # kind = 'user'
    agent_notes: int  # kind = 'note'
    people_posts_today: int  # human posts published today (tenant local day)
    agent_notes_today: int  # agent notes published today (tenant local day)
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
    # "today" in the tenant's own market timezone (Dhaka is UTC+6), not UTC — so the day boundary
    # matches what the operator experiences locally.
    try:
        local_now = now.astimezone(ZoneInfo(t.timezone))
    except Exception:
        local_now = now
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    since_24h = now - dt.timedelta(hours=24)
    since_7d = now - dt.timedelta(days=7)

    # people vs agent desks (both are User rows; desks carry is_official=true)
    users_desks = await _count(
        session,
        select(func.count())
        .select_from(User)
        .where(User.tenant_id == name, User.is_official.is_(True)),
    )
    users_total = await _count(
        session, select(func.count()).select_from(User).where(User.tenant_id == name)
    )
    users_people = users_total - users_desks

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

    agent_notes = await _count(
        session,
        select(func.count()).select_from(Post).where(Post.tenant_id == name, Post.kind == "note"),
    )
    user_posts = await _count(
        session,
        select(func.count()).select_from(Post).where(Post.tenant_id == name, Post.kind == "user"),
    )

    def _today(kind: str):
        return (
            select(func.count())
            .select_from(Post)
            .where(
                Post.tenant_id == name,
                Post.kind == kind,
                Post.moderation_status == "published",
                Post.created_at >= day_start,
            )
        )

    people_posts_today = await _count(session, _today("user"))
    agent_notes_today = await _count(session, _today("note"))
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
            .where(
                ModerationEvent.tenant_id == name, ModerationEvent.decision.in_(("hold", "block"))
            )
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
        select(func.count())
        .select_from(Symbol)
        .where(Symbol.market == market, Symbol.is_active.is_(True)),
    )
    symbols_hidden = await _count(
        session,
        select(func.count())
        .select_from(Symbol)
        .where(Symbol.market == market, Symbol.is_hidden.is_(True)),
    )

    return OverviewOut(
        tenant=name,
        market=market,
        generated_at=now,
        users_people=users_people,
        users_desks=users_desks,
        posts_total=posts_total,
        user_posts=user_posts,
        agent_notes=agent_notes,
        people_posts_today=people_posts_today,
        agent_notes_today=agent_notes_today,
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


# --- Analytics (time series + KPIs) ------------------------------------------------


class DailyPoint(BaseModel):
    date: str  # YYYY-MM-DD (tenant-local day)
    signups: int  # new real people that day
    public_posts: int  # published posts by people
    agent_notes: int  # published posts by desks
    reactions: int  # agree/disagree that day


class AnalyticsKpis(BaseModel):
    people_total: int
    desks_total: int
    new_people_7d: int
    new_people_30d: int
    active_people_7d: int  # distinct people who posted or reacted in the last 7 days
    public_posts_total: int
    agent_notes_total: int
    human_share_pct: float  # public posts / all published posts * 100
    reactions_7d: int


class AnalyticsOut(BaseModel):
    tenant: str
    market: str
    tz: str
    days: int
    generated_at: dt.datetime
    kpis: AnalyticsKpis
    series: list[DailyPoint]


def _local_day(col, tz: str):
    """A timestamptz column bucketed to the tenant-local calendar day (Postgres `AT TIME ZONE`)."""
    return cast(func.timezone(tz, col), Date)


async def _daily_counts(session, day_col, where) -> dict[str, int]:
    """Return {ISO date -> count} grouped by tenant-local day."""
    rows = await session.execute(select(day_col, func.count()).where(*where).group_by(day_col))
    return {str(d): int(n) for d, n in rows.all() if d is not None}


@router.get("/analytics")
async def analytics(
    request: Request,
    session: DbSession,
    tenant: str = Query(..., description="Tenant name (from /admin/tenants)"),
    days: int = Query(30, ge=7, le=180),
) -> AnalyticsOut:
    t = request.app.state.tenants.get(tenant)
    if t is None:
        raise HTTPException(status_code=404, detail=f"Unknown tenant: {tenant}")
    name, market, tz = t.name, t.market, t.timezone
    try:
        zone = ZoneInfo(tz)
    except Exception:
        zone, tz = ZoneInfo("UTC"), "UTC"

    now = dt.datetime.now(dt.UTC)
    today_local = now.astimezone(zone).date()
    start_local = today_local - dt.timedelta(days=days - 1)
    # UTC instant of local-window start, for the range filter.
    since = dt.datetime.combine(start_local, dt.time.min, tzinfo=zone).astimezone(dt.UTC)
    since_7d = now - dt.timedelta(days=7)
    since_30d = now - dt.timedelta(days=30)

    signup_day = _local_day(User.created_at, tz)
    post_day = _local_day(Post.created_at, tz)
    react_day = _local_day(PostReaction.created_at, tz)

    signups = await _daily_counts(
        session,
        signup_day,
        [User.tenant_id == name, User.is_official.is_(False), User.created_at >= since],
    )
    public_posts = await _daily_counts(
        session,
        post_day,
        [
            Post.tenant_id == name,
            Post.kind == "user",
            Post.moderation_status == "published",
            Post.created_at >= since,
        ],
    )
    agent_notes = await _daily_counts(
        session,
        post_day,
        [
            Post.tenant_id == name,
            Post.kind == "note",
            Post.moderation_status == "published",
            Post.created_at >= since,
        ],
    )
    # reactions need a join to scope by tenant; group by the reaction's local day.
    react_rows = await session.execute(
        select(react_day, func.count())
        .select_from(PostReaction)
        .join(Post, Post.id == PostReaction.post_id)
        .where(Post.tenant_id == name, PostReaction.created_at >= since)
        .group_by(react_day)
    )
    reactions = {str(d): int(n) for d, n in react_rows.all() if d is not None}

    series = []
    for i in range(days):
        d = str(start_local + dt.timedelta(days=i))
        series.append(
            DailyPoint(
                date=d,
                signups=signups.get(d, 0),
                public_posts=public_posts.get(d, 0),
                agent_notes=agent_notes.get(d, 0),
                reactions=reactions.get(d, 0),
            )
        )

    # KPIs
    people_total = await _count(
        session,
        select(func.count())
        .select_from(User)
        .where(User.tenant_id == name, User.is_official.is_(False)),
    )
    desks_total = await _count(
        session,
        select(func.count())
        .select_from(User)
        .where(User.tenant_id == name, User.is_official.is_(True)),
    )
    new_people_7d = await _count(
        session,
        select(func.count())
        .select_from(User)
        .where(User.tenant_id == name, User.is_official.is_(False), User.created_at >= since_7d),
    )
    new_people_30d = await _count(
        session,
        select(func.count())
        .select_from(User)
        .where(User.tenant_id == name, User.is_official.is_(False), User.created_at >= since_30d),
    )
    posters_7d = set(
        await session.scalars(
            select(distinct(Post.author_id)).where(
                Post.tenant_id == name, Post.kind == "user", Post.created_at >= since_7d
            )
        )
    )
    reactors_7d = set(
        await session.scalars(
            select(distinct(PostReaction.user_id))
            .join(Post, Post.id == PostReaction.post_id)
            .where(Post.tenant_id == name, PostReaction.created_at >= since_7d)
        )
    )
    public_posts_total = await _count(
        session,
        select(func.count()).select_from(Post).where(Post.tenant_id == name, Post.kind == "user"),
    )
    agent_notes_total = await _count(
        session,
        select(func.count()).select_from(Post).where(Post.tenant_id == name, Post.kind == "note"),
    )
    reactions_7d = await _count(
        session,
        select(func.count())
        .select_from(PostReaction)
        .join(Post, Post.id == PostReaction.post_id)
        .where(Post.tenant_id == name, PostReaction.created_at >= since_7d),
    )
    denom = public_posts_total + agent_notes_total
    human_share = round(public_posts_total / denom * 100, 1) if denom else 0.0

    return AnalyticsOut(
        tenant=name,
        market=market,
        tz=tz,
        days=days,
        generated_at=now,
        kpis=AnalyticsKpis(
            people_total=people_total,
            desks_total=desks_total,
            new_people_7d=new_people_7d,
            new_people_30d=new_people_30d,
            active_people_7d=len(posters_7d | reactors_7d),
            public_posts_total=public_posts_total,
            agent_notes_total=agent_notes_total,
            human_share_pct=human_share,
            reactions_7d=reactions_7d,
        ),
        series=series,
    )
