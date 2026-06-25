"""Run the levels-agent over the universe: detect → dedupe → publish notes into stock feeds.

    uv run python -m ingestion.signals.runner DSE   # one-shot

Detection re-derives yesterday from the bars, so it's safe to re-run — the signal_events ledger
(unique per occurrence) plus a per-event cooldown stop duplicate or repetitive notes.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import sys

from sqlalchemy import select

from bulls.analytics import compute
from bulls.core.db import get_sessionmaker
from bulls.core.models import Cashtag, DailyBar, Post, SignalEvent, Symbol
from ingestion.signals.agents import AGENTS, ensure_agents
from ingestion.signals.levels import BEAT, detect, render

_LOOKBACK = 260
_COOLDOWN_DAYS = 5  # don't repeat the same event on a name within this many days


async def _recent(session, market: str, code: str, event_type: str, today: dt.date) -> bool:
    """True if this (code, event_type) already fired within the cooldown — skip if so."""
    since = today - dt.timedelta(days=_COOLDOWN_DAYS)
    hit = await session.scalar(
        select(SignalEvent.id).where(
            SignalEvent.market == market,
            SignalEvent.code == code,
            SignalEvent.event_type == event_type,
            SignalEvent.as_of_date >= since,
        )
    )
    return hit is not None


async def run_levels_agent(
    market: str, *, tenant_id: str = "bullsofdhaka", locale: str = "bn"
) -> dict[str, int]:
    sm = get_sessionmaker()
    handle = AGENTS[BEAT][0]
    published = 0

    async with sm() as session:
        agent_id = (await ensure_agents(session, tenant_id))[BEAT]
        codes = list(
            await session.scalars(
                select(Symbol.code).where(
                    Symbol.market == market,
                    Symbol.is_active.is_(True),
                    Symbol.is_hidden.is_(False),
                )
            )
        )

        for code in codes:
            bars = list(
                await session.scalars(
                    select(DailyBar)
                    .where(DailyBar.market == market, DailyBar.code == code)
                    .order_by(DailyBar.date.desc())
                    .limit(_LOOKBACK)
                )
            )
            if len(bars) < 2:
                continue
            asc = list(reversed(bars))
            today = compute(asc)
            prev = compute(asc[:-1])

            for sig in detect(prev, today):
                if await _recent(session, market, code, sig.event_type, today.as_of_date):
                    continue
                exists = await session.scalar(
                    select(SignalEvent.id).where(
                        SignalEvent.market == market,
                        SignalEvent.code == code,
                        SignalEvent.event_type == sig.event_type,
                        SignalEvent.occurrence_key == sig.occurrence_key,
                    )
                )
                if exists:
                    continue
                post = Post(
                    tenant_id=tenant_id,
                    author_id=agent_id,
                    body=render(sig, code, locale),
                    kind="note",
                )
                session.add(post)
                await session.flush()
                session.add(Cashtag(post_id=post.id, market=market, code=code))
                session.add(
                    SignalEvent(
                        market=market,
                        code=code,
                        agent=handle,
                        event_type=sig.event_type,
                        occurrence_key=sig.occurrence_key,
                        post_id=post.id,
                        as_of_date=today.as_of_date,
                    )
                )
                published += 1
        await session.commit()

    return {"symbols": len(codes), "published": published}


async def _run(market: str) -> None:
    counts = await run_levels_agent(market)
    print(
        f"[signals/levels] {market}: published {counts['published']} notes over {counts['symbols']} names"
    )


def main() -> None:
    asyncio.run(_run(sys.argv[1] if len(sys.argv) > 1 else "DSE"))


if __name__ == "__main__":
    main()
