"""Record symbol page views — INTERNAL analytics only, never surfaced as a user-facing metric.

Fire-and-forget from the symbol page. Anonymous viewers are allowed (a client-supplied session id
de-dupes them at aggregation time); logged-in viewers are keyed by user. The buzz snapshot rolls
these up into ticker_buzz_daily.unique_viewers_24h. We deliberately do NOT return or display a
view count anywhere — page views are too noisy/gameable to show as a signal.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.deps import CurrentTenant, DbSession, OptionalUser
from bulls.core.models import PageViewEvent, Symbol

router = APIRouter(tags=["views"])


class ViewIn(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)  # anon client id (optional)


@router.post("/symbols/{code}/view", status_code=204)
async def record_view(
    code: str,
    body: ViewIn,
    tenant: CurrentTenant,
    session: DbSession,
    viewer: OptionalUser,
) -> None:
    code = code.upper()
    if await session.get(Symbol, (tenant.market, code)) is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")
    session.add(
        PageViewEvent(
            market=tenant.market,
            code=code,
            user_id=viewer.id if viewer else None,
            session_hash=body.session_id or None,
        )
    )
