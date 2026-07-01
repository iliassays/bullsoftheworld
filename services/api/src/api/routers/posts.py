"""Posts + feed + the conviction layer (reactions & replies).

Cashtags are parsed at write time and validated against the tenant's symbols. Posts thread via
`parent_id`; the top-level feed shows roots only. Reactions are agree/disagree — conviction on a
post's take, one per user per post — surfaced as tallies plus the caller's own stance.
"""

from __future__ import annotations

import datetime as dt
import re

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from api.deps import CurrentLocale, CurrentTenant, CurrentUser, DbSession, OptionalUser
from api.moderation import (
    moderate_new_post,
    normalized_hash,
    record_event,
    status_for,
)
from api.queue import enqueue_moderation, enqueue_sentiment
from bulls.core.config import get_settings
from bulls.core.models import (
    Cashtag,
    Follow,
    Post,
    PostReaction,
    QuoteSnapshot,
    Symbol,
    User,
    WatchlistItem,
)
from bulls.core.schemas.social import AuthorOut, PostCreate, PostOut, ReactionIn
from bulls.moderation import Action

router = APIRouter(prefix="/posts", tags=["posts"])

# Cashtag = $ followed by 2-16 uppercase alphanumerics.
CASHTAG_RE = re.compile(r"\$([A-Z0-9]{2,16})")


def parse_cashtags(body: str) -> list[str]:
    """Unique cashtag codes in order of first appearance."""
    return list(dict.fromkeys(CASHTAG_RE.findall(body.upper())))


async def _valid_codes(session, market: str, codes: list[str]) -> list[str]:
    """Keep only codes that exist as symbols in this market."""
    if not codes:
        return []
    rows = await session.scalars(
        select(Symbol.code).where(Symbol.market == market, Symbol.code.in_(codes))
    )
    found = set(rows)
    return [c for c in codes if c in found]


def _localized_body(p: Post, locale: str) -> str:
    """Agent notes carry both languages in body_i18n — serve the reader's pick. User posts have
    no body_i18n and are shown exactly as typed, in whatever language the author wrote them."""
    if p.body_i18n:
        return p.body_i18n.get(locale) or p.body
    return p.body


async def _decorate(
    session, posts: list[Post], *, viewer_id: int | None, locale: str
) -> list[PostOut]:
    """Attach authors, cashtags, reply counts, reaction tallies, and the caller's stance.

    Batched to avoid N+1 across a feed page.
    """
    if not posts:
        return []
    ids = [p.id for p in posts]

    authors = {
        u.id: u
        for u in await session.scalars(
            select(User).where(User.id.in_({p.author_id for p in posts}))
        )
    }
    tags: dict[int, list[str]] = {pid: [] for pid in ids}
    for ct in await session.scalars(select(Cashtag).where(Cashtag.post_id.in_(ids))):
        tags[ct.post_id].append(ct.code)

    # Latest price move per tagged code, so the cashtag chip can show +/- change (batched, no N+1).
    all_codes = {c for cs in tags.values() for c in cs}
    changes: dict[str, float] = {}
    if all_codes:
        for code, chg in (
            await session.execute(
                select(QuoteSnapshot.code, QuoteSnapshot.change_pct).where(
                    QuoteSnapshot.code.in_(all_codes)
                )
            )
        ).all():
            if chg is not None:
                changes[code] = round(chg, 2)

    reply_counts: dict[int, int] = {pid: 0 for pid in ids}
    for parent_id, n in (
        await session.execute(
            select(Post.parent_id, func.count())
            .where(Post.parent_id.in_(ids), Post.moderation_status == "published")
            .group_by(Post.parent_id)
        )
    ).all():
        reply_counts[parent_id] = n

    agree: dict[int, int] = {pid: 0 for pid in ids}
    disagree: dict[int, int] = {pid: 0 for pid in ids}
    for post_id, kind, n in (
        await session.execute(
            select(PostReaction.post_id, PostReaction.kind, func.count())
            .where(PostReaction.post_id.in_(ids))
            .group_by(PostReaction.post_id, PostReaction.kind)
        )
    ).all():
        (agree if kind == "agree" else disagree)[post_id] = n

    mine: dict[int, str] = {}
    if viewer_id is not None:
        for post_id, kind in (
            await session.execute(
                select(PostReaction.post_id, PostReaction.kind).where(
                    PostReaction.post_id.in_(ids), PostReaction.user_id == viewer_id
                )
            )
        ).all():
            mine[post_id] = kind

    out = []
    for p in posts:
        a = authors[p.author_id]
        out.append(
            PostOut(
                id=p.id,
                author=AuthorOut(handle=a.handle, name=a.name),
                body=_localized_body(p, locale),
                sentiment=p.sentiment,
                cashtags=tags.get(p.id, []),
                cashtag_changes={c: changes[c] for c in tags.get(p.id, []) if c in changes},
                image_url=p.image_url,
                created_at=p.created_at,
                kind=p.kind,
                parent_id=p.parent_id,
                reply_count=reply_counts.get(p.id, 0),
                agree=agree.get(p.id, 0),
                disagree=disagree.get(p.id, 0),
                my_reaction=mine.get(p.id),
                moderation_status=p.moderation_status,
                moderation_reason=p.moderation_reason,
            )
        )
    return out


@router.post("", status_code=201)
async def create_post(
    body: PostCreate, user: CurrentUser, tenant: CurrentTenant, session: DbSession
) -> PostOut:
    if body.parent_id is not None:
        parent = await session.get(Post, body.parent_id)
        if parent is None or parent.tenant_id != tenant.name:
            raise HTTPException(status_code=404, detail="Parent post not found")

    codes = await _valid_codes(session, tenant.market, parse_cashtags(body.body))
    route_code = body.route_code.upper() if body.route_code else None

    # Synchronous L0-L2 moderation (local, no AI). Clear violations block at write; the gray zone is
    # saved 'pending' (author-only, not public); clean posts publish. See docs/specs/feed-moderation.md.
    decision = await moderate_new_post(
        session,
        body=body.body,
        user=user,
        tenant_name=tenant.name,
        market=tenant.market,
        cashtags=codes,
        is_reply=body.parent_id is not None,
        route_code=route_code,
    )
    # Shadow rollout: when enforcement is off, the decision is still logged (below) but nothing is
    # blocked/held/masked — everything publishes. Flip MODERATION_ENFORCE=true to act on decisions.
    enforce = get_settings().moderation_enforce
    status = status_for(decision) if enforce else "published"
    stored_body = (
        decision.masked_body if (enforce and decision.action == Action.MASK) else body.body
    )

    post = Post(
        tenant_id=tenant.name,
        author_id=user.id,
        body=stored_body,
        sentiment=body.sentiment,
        parent_id=body.parent_id,
        moderation_status=status,
        moderation_reason=decision.reason_code,
        normalized_hash=normalized_hash(body.body),
    )
    session.add(post)
    await session.flush()

    # Blocked posts don't get cashtag rows — they must never reach a symbol feed or any tag aggregate.
    if status != "blocked":
        for code in codes:
            session.add(Cashtag(post_id=post.id, market=tenant.market, code=code))

    await record_event(session, post_id=post.id, tenant_name=tenant.name, decision=decision)
    await session.refresh(post)  # populate server-side created_at

    if enforce and decision.is_blocking:
        # Persist the blocked post + audit trail before rejecting (the dependency rolls back on raise).
        await session.commit()
        raise HTTPException(
            status_code=422,
            detail={
                "error": "blocked",
                "reason": decision.reason_code,
                "categories": [c.value for c in decision.categories],
            },
        )

    # commit before enqueuing so the worker can read the post; AI runs async, never blocks.
    await session.commit()
    if status == "published":
        # published user posts: auto-sentiment (if untagged) + the async L4 safety/relevance screen.
        if body.sentiment is None:
            await enqueue_sentiment(post.id)
        await enqueue_moderation(post.id)

    return PostOut(
        id=post.id,
        author=AuthorOut(handle=user.handle, name=user.name),
        body=post.body,
        sentiment=post.sentiment,
        cashtags=codes if status != "blocked" else [],
        created_at=post.created_at,
        parent_id=post.parent_id,
        moderation_status=post.moderation_status,
        moderation_reason=post.moderation_reason,
    )


@router.get("")
async def feed(
    tenant: CurrentTenant,
    session: DbSession,
    viewer: OptionalUser,
    locale: CurrentLocale,
    code: str | None = Query(None, description="Filter to posts tagging this symbol"),
    kind: str | None = Query(None, description="Filter by kind: 'note' = agent desk-notes only"),
    author: str | None = Query(
        None, description="Filter to one author handle (e.g. an agent beat in the Bulls feed)"
    ),
    watched: bool = Query(
        False, description="Only posts tagging the signed-in user's watchlist (ignored if no user)"
    ),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
) -> list[PostOut]:
    # Top-level feed shows roots only; replies are fetched per-thread. Only published posts are public
    # (pending/blocked never surface — see docs/specs/feed-moderation.md).
    stmt = select(Post).where(
        Post.tenant_id == tenant.name,
        Post.parent_id.is_(None),
        Post.moderation_status == "published",
    )
    if code:
        tagged = select(Cashtag.post_id).where(
            Cashtag.market == tenant.market, Cashtag.code == code.upper()
        )
        stmt = stmt.where(Post.id.in_(tagged))
    if kind:
        stmt = stmt.where(Post.kind == kind)
    if author:
        stmt = stmt.where(
            Post.author_id.in_(
                select(User.id).where(User.tenant_id == tenant.name, User.handle == author)
            )
        )
    if watched and viewer is not None:
        # Personalized Home = posts from desks you follow OR tagging companies you watch.
        watched_codes = select(WatchlistItem.code).where(
            WatchlistItem.user_id == viewer.id, WatchlistItem.market == tenant.market
        )
        followed = select(Follow.followee_id).where(Follow.follower_id == viewer.id)
        stmt = stmt.where(
            or_(
                Post.author_id.in_(followed),
                Post.id.in_(
                    select(Cashtag.post_id).where(
                        Cashtag.market == tenant.market, Cashtag.code.in_(watched_codes)
                    )
                ),
            )
        )
    stmt = stmt.order_by(Post.created_at.desc()).limit(limit).offset(offset)
    posts = list(await session.scalars(stmt))
    return await _decorate(session, posts, viewer_id=viewer.id if viewer else None, locale=locale)


class NoteBeat(BaseModel):
    """One agent beat with notes in the Bulls feed — drives the filter chips. Data-driven, so only
    beats that have actually posted appear (no empty chips), newest-active first."""

    handle: str
    name: str
    count: int


@router.get("/note-beats")
async def note_beats(tenant: CurrentTenant, session: DbSession) -> list[NoteBeat]:
    """Agent beats that have posted data notes (author handle + display name + how many), so the
    Bulls feed can offer filter chips by category (Circuit Limit, Accumulation, 52-Week, …)."""
    rows = await session.execute(
        select(User.handle, User.name, func.count(Post.id))
        .join(Post, Post.author_id == User.id)
        .where(
            Post.tenant_id == tenant.name,
            Post.kind == "note",
            Post.parent_id.is_(None),
            Post.moderation_status == "published",
        )
        .group_by(User.handle, User.name)
        .order_by(func.count(Post.id).desc())
    )
    return [NoteBeat(handle=h, name=n, count=c) for h, n, c in rows]


@router.get("/top")
async def top_post(
    tenant: CurrentTenant,
    session: DbSession,
    viewer: OptionalUser,
    locale: CurrentLocale,
    code: str = Query(..., description="Symbol code to find the most-discussed post for"),
    days: int = Query(7, ge=1, le=30),
) -> PostOut | None:
    """The single most-discussed post (reactions + replies) tagging `code` in the window, or None."""
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)
    tagged = select(Cashtag.post_id).where(
        Cashtag.market == tenant.market, Cashtag.code == code.upper()
    )
    candidates = list(
        await session.scalars(
            select(Post)
            .where(
                Post.tenant_id == tenant.name,
                Post.parent_id.is_(None),
                Post.id.in_(tagged),
                Post.created_at >= since,
                Post.moderation_status == "published",
            )
            .order_by(Post.created_at.desc())
            .limit(100)
        )
    )
    decorated = await _decorate(
        session, candidates, viewer_id=viewer.id if viewer else None, locale=locale
    )
    ranked = [p for p in decorated if (p.agree + p.disagree + p.reply_count) > 0]
    if not ranked:
        return None
    return max(ranked, key=lambda p: p.agree + p.disagree + p.reply_count)


@router.get("/{post_id}/replies")
async def replies(
    post_id: int,
    tenant: CurrentTenant,
    session: DbSession,
    viewer: OptionalUser,
    locale: CurrentLocale,
) -> list[PostOut]:
    children = list(
        await session.scalars(
            select(Post)
            .where(
                Post.tenant_id == tenant.name,
                Post.parent_id == post_id,
                Post.moderation_status == "published",
            )
            .order_by(Post.created_at.asc())
        )
    )
    return await _decorate(
        session, children, viewer_id=viewer.id if viewer else None, locale=locale
    )


@router.post("/{post_id}/react", status_code=200)
async def react(
    post_id: int,
    body: ReactionIn,
    user: CurrentUser,
    tenant: CurrentTenant,
    session: DbSession,
) -> dict[str, str]:
    post = await session.get(Post, post_id)
    if post is None or post.tenant_id != tenant.name or post.moderation_status != "published":
        raise HTTPException(status_code=404, detail="Post not found")
    existing = await session.get(PostReaction, (post_id, user.id))
    if existing is None:
        session.add(PostReaction(post_id=post_id, user_id=user.id, kind=body.kind))
    else:
        existing.kind = body.kind  # switching stance is an upsert
    return {"status": "ok", "kind": body.kind}


@router.delete("/{post_id}/react", status_code=204)
async def unreact(
    post_id: int, user: CurrentUser, tenant: CurrentTenant, session: DbSession
) -> None:
    existing = await session.get(PostReaction, (post_id, user.id))
    if existing is not None:
        await session.delete(existing)
