"""Record symbol page views — INTERNAL analytics only, never surfaced as a user-facing metric.

Fire-and-forget from the symbol page. Anonymous viewers are allowed (a client-supplied session id
de-dupes them at aggregation time); logged-in viewers are keyed by user. The buzz snapshot rolls
these up into ticker_buzz_daily.unique_viewers_24h. We deliberately do NOT return or display a
view count anywhere — page views are too noisy/gameable to show as a signal.
"""

from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from api.deps import CurrentTenant, DbSession, OptionalUser
from api.ratelimit import client_ip, throttle
from bulls.core.config import get_settings
from bulls.core.models import PageViewEvent, Symbol

router = APIRouter(tags=["views"])


class ViewIn(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)  # anon client id (optional)


def _anonymous_session_hash(tenant_id: str, session_id: str | None) -> str | None:
    if not session_id:
        return None
    return hmac.new(
        get_settings().jwt_secret.encode(),
        f"{tenant_id}:{session_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


@router.post("/symbols/{code}/view", status_code=204)
async def record_view(
    code: str,
    body: ViewIn,
    tenant: CurrentTenant,
    session: DbSession,
    viewer: OptionalUser,
    request: Request,
) -> None:
    await throttle(f"view:{tenant.name}:{client_ip(request)}", limit=300, window_s=3600)
    code = code.upper()
    symbol = await session.get(Symbol, (tenant.market, code))
    if symbol is None or not symbol.is_retail_ready:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")
    session.add(
        PageViewEvent(
            tenant_id=tenant.name,
            market=tenant.market,
            code=code,
            user_id=viewer.id if viewer else None,
            session_hash=_anonymous_session_hash(tenant.name, body.session_id),
        )
    )
