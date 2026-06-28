"""Posts + feed + the conviction layer (reactions & replies).

Cashtags are parsed at write time and validated against the tenant's symbols. Posts thread via
`parent_id`; the top-level feed shows roots only. Reactions are agree/disagree — conviction on a
post's take, one per user per post — surfaced as tallies plus the caller's own stance.
"""

from __future__ import annotations

import datetime as dt
import re

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from api.deps import CurrentLocale, CurrentTenant, CurrentUser, DbSession, OptionalUser
from api.queue import enqueue_sentiment
from bulls.core.models import Cashtag, Post, PostReaction, Symbol, User
from bulls.core.schemas.social import AuthorOut, PostCreate, PostOut, ReactionIn

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

    reply_counts: dict[int, int] = {pid: 0 for pid in ids}
    for parent_id, n in (
        await session.execute(
            select(Post.parent_id, func.count())
            .where(Post.parent_id.in_(ids))
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
                created_at=p.created_at,
                kind=p.kind,
                parent_id=p.parent_id,
                reply_count=reply_counts.get(p.id, 0),
                agree=agree.get(p.id, 0),
                disagree=disagree.get(p.id, 0),
                my_reaction=mine.get(p.id),
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

    post = Post(
        tenant_id=tenant.name,
        author_id=user.id,
        body=body.body,
        sentiment=body.sentiment,
        parent_id=body.parent_id,
    )
    session.add(post)
    await session.flush()

    codes = await _valid_codes(session, tenant.market, parse_cashtags(body.body))
    for code in codes:
        session.add(Cashtag(post_id=post.id, market=tenant.market, code=code))

    await session.refresh(post)  # populate server-side created_at
    # commit before enqueuing so the worker can read the post; AI runs async, never blocks.
    if body.sentiment is None:
        await session.commit()
        await enqueue_sentiment(post.id)

    return PostOut(
        id=post.id,
        author=AuthorOut(handle=user.handle, name=user.name),
        body=post.body,
        sentiment=post.sentiment,
        cashtags=codes,
        created_at=post.created_at,
        parent_id=post.parent_id,
    )


@router.get("")
async def feed(
    tenant: CurrentTenant,
    session: DbSession,
    viewer: OptionalUser,
    locale: CurrentLocale,
    code: str | None = Query(None, description="Filter to posts tagging this symbol"),
    kind: str | None = Query(None, description="Filter by kind: 'note' = agent desk-notes only"),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
) -> list[PostOut]:
    # Top-level feed shows roots only; replies are fetched per-thread.
    stmt = select(Post).where(Post.tenant_id == tenant.name, Post.parent_id.is_(None))
    if code:
        tagged = select(Cashtag.post_id).where(
            Cashtag.market == tenant.market, Cashtag.code == code.upper()
        )
        stmt = stmt.where(Post.id.in_(tagged))
    if kind:
        stmt = stmt.where(Post.kind == kind)
    stmt = stmt.order_by(Post.created_at.desc()).limit(limit).offset(offset)
    posts = list(await session.scalars(stmt))
    return await _decorate(session, posts, viewer_id=viewer.id if viewer else None, locale=locale)


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
            .where(Post.tenant_id == tenant.name, Post.parent_id == post_id)
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
    if post is None or post.tenant_id != tenant.name:
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
