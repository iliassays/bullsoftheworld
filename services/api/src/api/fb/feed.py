"""Publish agent cards (e.g. the Evening Wrap) into the in-app Bulls feed.

Renders the same branded card used on Facebook, saves it where the API serves /cards, and creates
a bilingual agent note carrying that image. Deduped per (market_wrap, ref_date) — shares the ledger
key with the market-update agent, so the feed never shows a duplicate wrap.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from pathlib import Path

from sqlalchemy import select

from api.fb import cards, compose
from bulls.core.config import get_settings
from bulls.core.models import Post, SignalEvent, User

_MARKET_AGENT = "BullsOfDhakaMarket"
_MARKET_CODE = "MARKET"
_EVENT = "market_wrap"


class FeedPublishError(RuntimeError):
    pass


def _render_and_save(data: cards.EveningWrapData, card_dir: str, fname: str) -> None:
    """Blocking render + file write — run in a thread (rsvg subprocess + disk I/O)."""
    d = Path(card_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / fname).write_bytes(cards.evening_wrap_card(data))


async def publish_evening_wrap_to_feed(
    session, market: str, *, tenant_id: str, force: bool = False
) -> dict:
    data, ref_date = await compose.build_evening_data(session, market)

    existing = await session.scalar(
        select(SignalEvent).where(
            SignalEvent.tenant_id == tenant_id,
            SignalEvent.market == market,
            SignalEvent.code == _MARKET_CODE,
            SignalEvent.event_type == _EVENT,
            SignalEvent.occurrence_key == ref_date,
        )
    )
    if existing and not force:
        return {"status": "already_posted", "post_id": existing.post_id, "ref_date": ref_date}

    agent = await session.scalar(
        select(User).where(User.tenant_id == tenant_id, User.handle == _MARKET_AGENT)
    )
    if agent is None:
        raise FeedPublishError(f"agent {_MARKET_AGENT} not found (seed signal agents first)")

    s = get_settings()
    fname = f"{tenant_id}-evening-wrap-{ref_date}.png"
    await asyncio.to_thread(_render_and_save, data, s.card_dir, fname)
    image_url = f"{s.api_public_url.rstrip('/')}/cards/{fname}"

    bodies = compose.evening_bodies(data)
    post = Post(
        tenant_id=tenant_id,
        author_id=agent.id,
        kind="note",
        body=bodies["bn"],
        body_i18n=bodies,
        image_url=image_url,
    )
    session.add(post)
    await session.flush()
    if existing:  # force re-post → repoint the ledger at the new note
        existing.post_id = post.id
    else:
        session.add(
            SignalEvent(
                tenant_id=tenant_id,
                market=market,
                code=_MARKET_CODE,
                agent=_MARKET_AGENT,
                event_type=_EVENT,
                occurrence_key=ref_date,
                post_id=post.id,
                as_of_date=dt.date.fromisoformat(ref_date),
            )
        )
    await session.commit()
    return {"status": "posted", "post_id": post.id, "ref_date": ref_date, "image_url": image_url}
