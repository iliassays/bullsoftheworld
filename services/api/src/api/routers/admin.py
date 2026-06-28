"""Admin routes — symbol visibility curation. Guarded by the shared admin token.

Used to hide non-equity instruments (bonds, mutual funds, debentures) and any junk from the retail
view. `is_hidden` is a manual override the scraper never touches, so a hide sticks across polls.
"""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from api import facebook
from api.deps import CurrentTenant, DbSession, require_admin
from api.fb import compose as fbcompose
from api.fb import feed as fbfeed
from bulls.core.config import get_settings
from bulls.core.models import Symbol

# pillar key -> composer; add a pillar by adding its composer here
_FB_COMPOSERS = {
    "evening_wrap": fbcompose.compose_evening_wrap,
    "morning_watch": fbcompose.compose_morning_watch,
    "weekly_recap": fbcompose.compose_weekly_recap,
}

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class VisibilityIn(BaseModel):
    codes: list[str]
    hidden: bool


class AdminSymbol(BaseModel):
    code: str
    name_en: str
    category: str | None
    is_active: bool
    is_hidden: bool


@router.get("/symbols")
async def list_all_symbols(
    tenant: CurrentTenant, session: DbSession, hidden: bool | None = None
) -> list[AdminSymbol]:
    """All symbols with their active/hidden flags (optionally filtered by hidden)."""
    stmt = select(Symbol).where(Symbol.market == tenant.market)
    if hidden is not None:
        stmt = stmt.where(Symbol.is_hidden.is_(hidden))
    rows = await session.scalars(stmt.order_by(Symbol.code))
    return [
        AdminSymbol(
            code=s.code,
            name_en=s.name_en,
            category=s.category,
            is_active=s.is_active,
            is_hidden=s.is_hidden,
        )
        for s in rows
    ]


@router.post("/symbols/visibility")
async def set_visibility(
    body: VisibilityIn, tenant: CurrentTenant, session: DbSession
) -> dict[str, int | bool]:
    """Hide or unhide a batch of symbols. Returns how many rows changed."""
    codes = [c.strip().upper() for c in body.codes if c.strip()]
    if not codes:
        return {"updated": 0, "hidden": body.hidden}
    result = await session.execute(
        update(Symbol)
        .where(Symbol.market == tenant.market, Symbol.code.in_(codes))
        .values(is_hidden=body.hidden)
    )
    return {"updated": result.rowcount or 0, "hidden": body.hidden}


# --- Facebook page posting (admin-gated) ---------------------------------------


class FbPostIn(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    link: str | None = None
    image_url: str | None = None  # if set, posts a photo with `message` as caption


@router.get("/fb/status")
async def fb_status() -> dict:
    """Verify the Page token works (non-publishing): returns page name + follower count."""
    try:
        return await facebook.page_info()
    except facebook.FacebookError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/fb/post")
async def fb_post(body: FbPostIn) -> dict:
    """Publish a post to the Bulls of Dhaka page. Photo if image_url is given, else text/link."""
    try:
        if body.image_url:
            post_id = await facebook.post_photo(body.image_url, body.message)
        else:
            post_id = await facebook.post_text(body.message, body.link)
        return {"status": "posted", "post_id": post_id}
    except facebook.FacebookError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


async def _compose(kind: str, session, market: str) -> fbcompose.ComposedPost:
    fn = _FB_COMPOSERS.get(kind)
    if fn is None:
        raise HTTPException(status_code=404, detail=f"unknown post kind: {kind}")
    try:
        return await fn(session, market)
    except Exception as e:  # compose/render errors → 400 with reason
        raise HTTPException(status_code=400, detail=f"compose failed: {e}") from e


@router.get("/fb/card")
async def fb_card(
    tenant: CurrentTenant, session: DbSession, kind: str = Query("evening_wrap")
) -> Response:
    """Render the branded card PNG for a pillar (preview only — does not post)."""
    post = await _compose(kind, session, tenant.market)
    return Response(content=post.png, media_type="image/png")


@router.get("/fb/preview")
async def fb_preview(
    tenant: CurrentTenant, session: DbSession, kind: str = Query("evening_wrap")
) -> dict:
    """Preview the caption + card link for a pillar without posting."""
    post = await _compose(kind, session, tenant.market)
    return {
        "kind": post.kind,
        "ref_date": post.ref_date,
        "caption": post.caption,
        "card_url": f"/admin/fb/card?kind={kind}",
    }


@router.post("/fb/publish")
async def fb_publish(
    tenant: CurrentTenant,
    session: DbSession,
    kind: str = Query("evening_wrap"),
    force: bool = Query(False, description="Repost even if already posted for this ref_date"),
) -> dict:
    """Compose + publish a pillar's card to the page. Idempotent per (kind, ref_date)."""
    post = await _compose(kind, session, tenant.market)
    key = f"fb:posted:{kind}:{post.ref_date}"
    redis = aioredis.from_url(get_settings().redis_url)
    try:
        if not force and (existing := await redis.get(key)):
            return {"status": "already_posted", "post_id": existing.decode(), "ref_date": post.ref_date}
        try:
            post_id = await facebook.post_photo_bytes(post.png, post.caption)
        except facebook.FacebookError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        await redis.set(key, post_id, ex=7 * 24 * 3600)
        return {"status": "posted", "post_id": post_id, "ref_date": post.ref_date}
    finally:
        await redis.aclose()


@router.post("/fb/publish-feed")
async def fb_publish_feed(
    tenant: CurrentTenant,
    session: DbSession,
    kind: str = Query("evening_wrap"),
    force: bool = Query(False, description="Repost even if already in the feed for this ref_date"),
) -> dict:
    """Publish a pillar's card into the in-app Bulls feed (agent note + card image)."""
    if kind != "evening_wrap":
        raise HTTPException(status_code=404, detail=f"unsupported feed kind: {kind}")
    try:
        return await fbfeed.publish_evening_wrap_to_feed(
            session, tenant.market, tenant_id=tenant.name, force=force
        )
    except (fbfeed.FeedPublishError, fbcompose.cards.CardError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
