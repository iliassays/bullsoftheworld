"""Shared publish + dedupe for all agents — one note per occurrence, with a per-event cooldown.

Keeps every agent posting the same way: a Post (kind=note, authored by the agent) + a Cashtag (so
it lands on the ticker feed) + a signal_events ledger row.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import or_, select

from bulls.core.models import Cashtag, Post, SignalEvent
from ingestion.alerts import fan_out_note_alert


async def already_fired(
    session,
    market: str,
    code: str,
    event_type: str,
    occurrence_key: str,
    *,
    tenant_id: str,
    today: dt.date,
    cooldown_days: int,
) -> bool:
    """True if this exact occurrence already posted, or the same event fired within the cooldown."""
    since = today - dt.timedelta(days=cooldown_days)
    hit = await session.scalar(
        select(SignalEvent.id).where(
            SignalEvent.tenant_id == tenant_id,
            SignalEvent.market == market,
            SignalEvent.code == code,
            SignalEvent.event_type == event_type,
            or_(SignalEvent.occurrence_key == occurrence_key, SignalEvent.as_of_date >= since),
        )
    )
    return hit is not None


async def publish_note(
    session,
    *,
    tenant_id: str,
    market: str,
    code: str,
    agent_id: int,
    agent_handle: str,
    event_type: str,
    occurrence_key: str,
    body: str | None = None,
    body_i18n: dict[str, str] | None = None,
    as_of: dt.date | None,
    add_cashtag: bool = True,
) -> None:
    # Notes are rendered from bilingual templates: store both languages so the feed can serve
    # whichever the reader picked. `body` (non-null Text) keeps the Bangla default for back-compat.
    if body is None:
        if not body_i18n:
            raise ValueError("publish_note needs body or body_i18n")
        body = body_i18n.get("bn") or next(iter(body_i18n.values()))
    post = Post(
        tenant_id=tenant_id, author_id=agent_id, body=body, body_i18n=body_i18n, kind="note"
    )
    session.add(post)
    await session.flush()
    if add_cashtag:
        # a real ticker note lands on that symbol's feed; market-wide notes carry no cashtag
        session.add(Cashtag(post_id=post.id, market=market, code=code))
    session.add(
        SignalEvent(
            tenant_id=tenant_id,
            market=market,
            code=code,
            agent=agent_handle,
            event_type=event_type,
            occurrence_key=occurrence_key,
            post_id=post.id,
            as_of_date=as_of,
        )
    )
    if add_cashtag:
        # Ticker events also land in the alert inbox of everyone watching/holding the stock.
        # Market-wide notes (no cashtag) stay feed-only — the feed already reaches everyone.
        await fan_out_note_alert(
            session,
            tenant_id=tenant_id,
            market=market,
            code=code,
            event_type=event_type,
            body_i18n=body_i18n,
            ref_post_id=post.id,
        )
