"""Run the levels-agent over the universe: detect → dedupe → publish notes into stock feeds.

    uv run python -m ingestion.signals.runner DSE   # one-shot

Detection re-derives yesterday from the bars, so it's safe to re-run — the signal_events ledger
(unique per occurrence) plus a per-event cooldown stop duplicate or repetitive notes.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from bulls.analytics import compute
from bulls.core.db import get_sessionmaker
from bulls.core.models import DailyBar, ShareholdingSnapshot, Symbol
from ingestion.signals import ownership
from ingestion.signals.agents import AGENTS, ensure_agents
from ingestion.signals.levels import BEAT, detect, render
from ingestion.signals.publish import already_fired, publish_note

_LOOKBACK = 260
_COOLDOWN_DAYS = 5  # don't repeat the same event on a name within this many days
_OWN_COOLDOWN_DAYS = 20  # ownership discloses monthly — don't refire within a disclosure window


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
                if await already_fired(
                    session,
                    market,
                    code,
                    sig.event_type,
                    sig.occurrence_key,
                    today=today.as_of_date,
                    cooldown_days=_COOLDOWN_DAYS,
                ):
                    continue
                await publish_note(
                    session,
                    tenant_id=tenant_id,
                    market=market,
                    code=code,
                    agent_id=agent_id,
                    agent_handle=handle,
                    event_type=sig.event_type,
                    occurrence_key=sig.occurrence_key,
                    body=render(sig, code, locale),
                    as_of=today.as_of_date,
                )
                published += 1
        await session.commit()

    return {"symbols": len(codes), "published": published}


async def run_ownership_agents(
    market: str, *, tenant_id: str = "bullsofdhaka", locale: str = "bn"
) -> dict[str, int]:
    """Compare each symbol's two latest shareholding disclosures; post material stake changes."""
    sm = get_sessionmaker()
    published = 0
    async with sm() as session:
        ids = await ensure_agents(session, tenant_id)
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
            snaps = list(
                await session.scalars(
                    select(ShareholdingSnapshot)
                    .where(ShareholdingSnapshot.market == market, ShareholdingSnapshot.code == code)
                    .order_by(ShareholdingSnapshot.as_of_date.desc())
                    .limit(2)
                )
            )
            if len(snaps) < 2:
                continue
            latest, prev = snaps[0], snaps[1]
            for sig in ownership.detect(prev, latest):
                if await already_fired(
                    session,
                    market,
                    code,
                    sig.event_type,
                    sig.occurrence_key,
                    today=latest.as_of_date,
                    cooldown_days=_OWN_COOLDOWN_DAYS,
                ):
                    continue
                handle = AGENTS[sig.beat][0]
                await publish_note(
                    session,
                    tenant_id=tenant_id,
                    market=market,
                    code=code,
                    agent_id=ids[sig.beat],
                    agent_handle=handle,
                    event_type=sig.event_type,
                    occurrence_key=sig.occurrence_key,
                    body=ownership.render(sig, code, locale),
                    as_of=latest.as_of_date,
                )
                published += 1
        await session.commit()
    return {"symbols": len(codes), "published": published}


async def _run(market: str) -> None:
    lv = await run_levels_agent(market)
    ow = await run_ownership_agents(market)
    print(f"[signals] {market}: levels={lv['published']} ownership={ow['published']}")


def main() -> None:
    asyncio.run(_run(sys.argv[1] if len(sys.argv) > 1 else "DSE"))


if __name__ == "__main__":
    main()
