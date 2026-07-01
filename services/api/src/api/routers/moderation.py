"""Review queue (docs/specs/feed-moderation.md §6). Admin-guarded — for the human reviewer.

Lists posts the synchronous cascade parked as `pending` (gray zone) or `held`, with the context needed
to decide: the reason, categories, risk, matched rules, cashtags, author and account age. Approve
publishes; block rejects. Every reviewer action appends a `moderation_event` (actor='reviewer'), so the
audit trail stays complete. Held posts are never auto-published — a human decides, or they expire hidden.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select

from api.deps import CurrentTenant, DbSession, require_admin
from api.moderation import record_event
from bulls.core.models import Cashtag, ModerationEvent, Post, User
from bulls.moderation import Action, Category, Decision

router = APIRouter(prefix="/moderation", tags=["moderation"], dependencies=[Depends(require_admin)])


class QueueItem(BaseModel):
    post_id: int
    author_handle: str
    author_name: str
    account_age_days: int | None
    body: str
    cashtags: list[str]
    status: str
    reason: str | None
    categories: list[str]
    risk_score: float | None
    rule_ids: list[str]
    created_at: dt.datetime


class QueueOut(BaseModel):
    count: int
    items: list[QueueItem]


@router.get("/queue")
async def queue(
    tenant: CurrentTenant,
    session: DbSession,
    status: str = Query("pending", pattern="^(pending|held)$"),
    limit: int = Query(50, le=200),
) -> QueueOut:
    posts = list(
        await session.scalars(
            select(Post)
            .where(Post.tenant_id == tenant.name, Post.moderation_status == status)
            .order_by(Post.created_at.asc())  # oldest first — clear the backlog fairly
            .limit(limit)
        )
    )
    if not posts:
        return QueueOut(count=0, items=[])

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

    # Latest system event per post, for the reason/risk/rules context.
    latest: dict[int, ModerationEvent] = {}
    for ev in await session.scalars(
        select(ModerationEvent)
        .where(ModerationEvent.post_id.in_(ids))
        .order_by(ModerationEvent.post_id, desc(ModerationEvent.created_at))
    ):
        latest.setdefault(ev.post_id, ev)

    now = dt.datetime.now(dt.UTC)
    items = []
    for p in posts:
        a = authors.get(p.author_id)
        ev = latest.get(p.id)
        age = None
        if a is not None and a.created_at is not None:
            created = a.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=dt.UTC)
            age = int((now - created).total_seconds() // 86400)
        items.append(
            QueueItem(
                post_id=p.id,
                author_handle=a.handle if a else "?",
                author_name=a.name if a else "?",
                account_age_days=age,
                body=p.body,
                cashtags=tags.get(p.id, []),
                status=p.moderation_status,
                reason=p.moderation_reason,
                categories=list(ev.categories or []) if ev else [],
                risk_score=float(ev.risk_score) if ev and ev.risk_score is not None else None,
                rule_ids=list(ev.rule_ids or []) if ev else [],
                created_at=p.created_at,
            )
        )
    return QueueOut(count=len(items), items=items)


@router.get("/stats")
async def stats(tenant: CurrentTenant, session: DbSession) -> dict[str, int]:
    """Queue depth by status — for a quick health glance (backlog is the risk to watch)."""
    rows = await session.execute(
        select(Post.moderation_status, func.count())
        .where(Post.tenant_id == tenant.name)
        .group_by(Post.moderation_status)
    )
    return {status: n for status, n in rows}


async def _set_status(
    session, tenant_name: str, post_id: int, new_status: str, action: Action, note: str | None
) -> Post:
    post = await session.get(Post, post_id)
    if post is None or post.tenant_id != tenant_name:
        raise HTTPException(status_code=404, detail="Post not found")
    post.moderation_status = new_status
    await record_event(
        session,
        post_id=post.id,
        tenant_name=tenant_name,
        decision=Decision(action=action, categories=[Category.CLEAN], layer=0),
        actor="reviewer",
        note=note,
    )
    return post


class ReviewNote(BaseModel):
    note: str | None = None


@router.post("/{post_id}/approve")
async def approve(
    post_id: int, tenant: CurrentTenant, session: DbSession, body: ReviewNote | None = None
) -> dict[str, str]:
    """Clear a pending/held post to the public feed."""
    await _set_status(
        session, tenant.name, post_id, "published", Action.ALLOW, body.note if body else None
    )
    return {"status": "published"}


@router.post("/{post_id}/block")
async def block(
    post_id: int, tenant: CurrentTenant, session: DbSession, body: ReviewNote | None = None
) -> dict[str, str]:
    """Reject a pending/held post."""
    await _set_status(
        session, tenant.name, post_id, "blocked", Action.BLOCK, body.note if body else None
    )
    return {"status": "blocked"}
