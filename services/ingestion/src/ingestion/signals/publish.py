"""Shared publish + dedupe for all agents — one note per occurrence, with a per-event cooldown.

Keeps every agent posting the same way: a Post (kind=note, authored by the agent) + a Cashtag (so
it lands on the ticker feed) + a signal_events ledger row.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import or_, select

from bulls.core.models import Cashtag, Post, SignalEvent


async def already_fired(
    session,
    market: str,
    code: str,
    event_type: str,
    occurrence_key: str,
    *,
    today: dt.date,
    cooldown_days: int,
) -> bool:
    """True if this exact occurrence already posted, or the same event fired within the cooldown."""
    since = today - dt.timedelta(days=cooldown_days)
    hit = await session.scalar(
        select(SignalEvent.id).where(
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
    body: str,
    as_of: dt.date | None,
) -> None:
    post = Post(tenant_id=tenant_id, author_id=agent_id, body=body, kind="note")
    session.add(post)
    await session.flush()
    session.add(Cashtag(post_id=post.id, market=market, code=code))
    session.add(
        SignalEvent(
            market=market,
            code=code,
            agent=agent_handle,
            event_type=event_type,
            occurrence_key=occurrence_key,
            post_id=post.id,
            as_of_date=as_of,
        )
    )
