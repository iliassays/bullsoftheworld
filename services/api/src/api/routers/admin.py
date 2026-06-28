"""Admin routes — symbol visibility curation. Guarded by the shared admin token.

Used to hide non-equity instruments (bonds, mutual funds, debentures) and any junk from the retail
view. `is_hidden` is a manual override the scraper never touches, so a hide sticks across polls.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from api import facebook
from api.deps import CurrentTenant, DbSession, require_admin
from bulls.core.models import Symbol

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
