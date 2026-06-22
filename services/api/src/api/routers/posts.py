"""Posts + feed. Cashtags are parsed at write time and validated against the tenant's symbols."""

from __future__ import annotations

import re

from fastapi import APIRouter, Query
from sqlalchemy import select

from api.deps import CurrentTenant, CurrentUser, DbSession
from bulls.core.models import Cashtag, Post, Symbol, User
from bulls.core.schemas.social import AuthorOut, PostCreate, PostOut

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


@router.post("", status_code=201)
async def create_post(
    body: PostCreate, user: CurrentUser, tenant: CurrentTenant, session: DbSession
) -> PostOut:
    post = Post(tenant_id=tenant.name, author_id=user.id, body=body.body, sentiment=body.sentiment)
    session.add(post)
    await session.flush()

    codes = await _valid_codes(session, tenant.market, parse_cashtags(body.body))
    for code in codes:
        session.add(Cashtag(post_id=post.id, market=tenant.market, code=code))

    await session.refresh(post)  # populate server-side created_at
    return PostOut(
        id=post.id,
        author=AuthorOut(handle=user.handle, name=user.name),
        body=post.body,
        sentiment=post.sentiment,
        cashtags=codes,
        created_at=post.created_at,
    )


@router.get("")
async def feed(
    tenant: CurrentTenant,
    session: DbSession,
    code: str | None = Query(None, description="Filter to posts tagging this symbol"),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
) -> list[PostOut]:
    stmt = select(Post).where(Post.tenant_id == tenant.name)
    if code:
        tagged = select(Cashtag.post_id).where(
            Cashtag.market == tenant.market, Cashtag.code == code.upper()
        )
        stmt = stmt.where(Post.id.in_(tagged))
    stmt = stmt.order_by(Post.created_at.desc()).limit(limit).offset(offset)
    posts = list(await session.scalars(stmt))
    if not posts:
        return []

    # batch-load authors and cashtags to avoid N+1
    author_ids = {p.author_id for p in posts}
    authors = {u.id: u for u in await session.scalars(select(User).where(User.id.in_(author_ids)))}
    post_ids = [p.id for p in posts]
    tags: dict[int, list[str]] = {pid: [] for pid in post_ids}
    for ct in await session.scalars(select(Cashtag).where(Cashtag.post_id.in_(post_ids))):
        tags[ct.post_id].append(ct.code)

    out = []
    for p in posts:
        a = authors[p.author_id]
        out.append(
            PostOut(
                id=p.id,
                author=AuthorOut(handle=a.handle, name=a.name),
                body=p.body,
                sentiment=p.sentiment,
                cashtags=tags.get(p.id, []),
                created_at=p.created_at,
            )
        )
    return out
