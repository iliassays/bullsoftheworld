"""Run the levels-agent over the universe: detect → dedupe → publish notes into stock feeds.

    uv run python -m ingestion.signals.runner DSE   # one-shot

Detection re-derives yesterday from the bars, so it's safe to re-run — the signal_events ledger
(unique per occurrence) plus a per-event cooldown stop duplicate or repetitive notes.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import sys

from sqlalchemy import func, or_, select

from bulls.analytics import compute
from bulls.analytics.indicators import index_change_pct
from bulls.core.db import get_sessionmaker
from bulls.core.models import (
    DailyBar,
    MarketSummary,
    QuoteSnapshot,
    ShareholdingSnapshot,
    Symbol,
    TickerAnalytics,
)
from bulls.market_data.calendar import to_market_tz
from ingestion.signals import factors, ownership, volume
from ingestion.signals import market as market_wrap
from ingestion.signals.agents import AGENTS, ensure_agents
from ingestion.signals.levels import BEAT, detect, render
from ingestion.signals.publish import already_fired, publish_note

_LOOKBACK = 260
_COOLDOWN_DAYS = 5  # don't repeat the same event on a name within this many days
_OWN_COOLDOWN_DAYS = 20  # ownership discloses monthly — don't refire within a disclosure window


async def run_levels_agent(market: str, *, tenant_id: str = "bullsofdhaka") -> dict[str, int]:
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
                    body_i18n={"bn": render(sig, code, "bn"), "en": render(sig, code, "en")},
                    as_of=today.as_of_date,
                )
                published += 1
        await session.commit()

    return {"symbols": len(codes), "published": published}


async def run_ownership_agents(market: str, *, tenant_id: str = "bullsofdhaka") -> dict[str, int]:
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
                    .limit(6)  # pairwise needs 2; the falling-streak detector reads the run
                )
            )
            if len(snaps) < 2:
                continue
            latest, prev = snaps[0], snaps[1]
            sigs = ownership.detect(prev, latest)
            streak = ownership.detect_sponsor_streak(snaps)
            if streak is not None:
                sigs.append(streak)
            for sig in sigs:
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
                    body_i18n={
                        "bn": ownership.render(sig, code, "bn"),
                        "en": ownership.render(sig, code, "en"),
                    },
                    as_of=latest.as_of_date,
                )
                published += 1
        await session.commit()
    return {"symbols": len(codes), "published": published}


async def run_volume_agent(market: str, *, tenant_id: str = "bullsofdhaka") -> dict[str, int]:
    """Flag unusual intraday volume vs the expected-by-now pace. Fires once per name per day."""
    now = dt.datetime.now(dt.UTC)
    fraction = volume.session_fraction(now)
    today = to_market_tz(now).date()
    day = str(today)
    sm = get_sessionmaker()
    published = 0
    async with sm() as session:
        agent_id = (await ensure_agents(session, tenant_id))[volume.BEAT]
        handle = AGENTS[volume.BEAT][0]
        rows = (
            await session.execute(
                select(
                    QuoteSnapshot.code,
                    QuoteSnapshot.volume,
                    QuoteSnapshot.as_of,
                    TickerAnalytics.avg_volume_20,
                    QuoteSnapshot.change_pct,
                )
                .join(
                    TickerAnalytics,
                    (QuoteSnapshot.market == TickerAnalytics.market)
                    & (QuoteSnapshot.code == TickerAnalytics.code),
                )
                .join(
                    Symbol,
                    (QuoteSnapshot.market == Symbol.market) & (QuoteSnapshot.code == Symbol.code),
                )
                .where(
                    QuoteSnapshot.market == market,
                    Symbol.is_active.is_(True),
                    Symbol.is_hidden.is_(False),
                    # promotional-flavoured beats never post on Z junk (pump amplification)
                    or_(Symbol.category.is_(None), Symbol.category != "Z"),
                )
            )
        ).all()
        for code, vol, as_of, avg, change_pct in rows:
            # only flag on a fresh quote from today's session — a stale quote vs a tiny
            # expected-by-now would massively over-fire
            if as_of is None or to_market_tz(as_of).date() != today:
                continue
            sig = volume.detect(vol, avg, fraction, day, change_pct)
            if sig is None:
                continue
            if await already_fired(
                session,
                market,
                code,
                sig.event_type,
                sig.occurrence_key,
                today=today,
                cooldown_days=1,
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
                body_i18n={
                    "bn": volume.render(sig, code, "bn"),
                    "en": volume.render(sig, code, "en"),
                },
                as_of=today,
            )
            published += 1
        await session.commit()
    return {"published": published}


async def run_factor_agents(market: str, *, tenant_id: str = "bullsofdhaka") -> dict[str, int]:
    """Descriptive factor notes (momentum / quality-value / smart-money / relative strength) from the
    precomputed analytics row + today's price vs the index. Once per name per factor per month."""
    now = dt.datetime.now(dt.UTC)
    local = to_market_tz(now).date()
    month_key = local.strftime("%Y-%m")
    day = str(local)
    sm = get_sessionmaker()
    published = 0
    async with sm() as session:
        ids = await ensure_agents(session, tenant_id)
        # dsex_change is stored in POINTS (as DSE reports it) — convert to the day's % move
        # before comparing against per-stock change_pct (the "DSEX fell 19.0%" incident).
        idx_row = (
            await session.execute(
                select(MarketSummary.dsex, MarketSummary.dsex_change)
                .where(MarketSummary.market == market, MarketSummary.dsex_change.isnot(None))
                .order_by(MarketSummary.date.desc())
                .limit(1)
            )
        ).first()
        dsex_change_pct = index_change_pct(idx_row.dsex, idx_row.dsex_change) if idx_row else None
        rows = (
            await session.execute(
                select(TickerAnalytics, QuoteSnapshot.change_pct)
                .join(
                    QuoteSnapshot,
                    (TickerAnalytics.market == QuoteSnapshot.market)
                    & (TickerAnalytics.code == QuoteSnapshot.code),
                    isouter=True,
                )
                .join(
                    Symbol,
                    (TickerAnalytics.market == Symbol.market)
                    & (TickerAnalytics.code == Symbol.code),
                )
                .where(
                    TickerAnalytics.market == market,
                    Symbol.is_active.is_(True),
                    Symbol.is_hidden.is_(False),
                    # promotional-flavoured beats never post on Z junk (pump amplification)
                    or_(Symbol.category.is_(None), Symbol.category != "Z"),
                )
            )
        ).all()
        for ta, change_pct in rows:
            sigs = [
                factors.detect_momentum(ta, month_key),
                factors.detect_quality(ta, month_key),
                factors.detect_smartmoney(ta, month_key),
                factors.detect_accumulation(ta, month_key),
                factors.detect_strength(change_pct, dsex_change_pct, day),
                # ta.last_close = latest EOD close ≈ today's reference price for the band tier.
                factors.detect_circuit(change_pct, day, ta.last_close),
                factors.detect_breakout(ta, change_pct, day),
            ]
            for sig in sigs:
                if sig is None:
                    continue
                if await already_fired(
                    session,
                    market,
                    ta.code,
                    sig.event_type,
                    sig.occurrence_key,
                    today=ta.as_of_date,
                    cooldown_days=sig.cooldown_days,
                ):
                    continue
                await publish_note(
                    session,
                    tenant_id=tenant_id,
                    market=market,
                    code=ta.code,
                    agent_id=ids[sig.beat],
                    agent_handle=AGENTS[sig.beat][0],
                    event_type=sig.event_type,
                    occurrence_key=sig.occurrence_key,
                    body_i18n={
                        "bn": factors.render(sig, ta.code, "bn"),
                        "en": factors.render(sig, ta.code, "en"),
                    },
                    as_of=ta.as_of_date,
                )
                published += 1
        await session.commit()
    return {"symbols": len(rows), "published": published}


async def run_market_update(market: str, *, tenant_id: str = "bullsofdhaka") -> dict[str, int]:
    """One market-wide close wrap (DSEX + breadth + turnover). No cashtag — global feed only."""
    sm = get_sessionmaker()
    async with sm() as session:
        agent_id = (await ensure_agents(session, tenant_id))[market_wrap.BEAT]
        summary = await session.scalar(
            select(MarketSummary)
            .where(MarketSummary.market == market)
            .order_by(MarketSummary.date.desc())
            .limit(1)
        )
        if summary is None:
            return {"published": 0}
        adv = await session.scalar(
            select(func.count()).where(QuoteSnapshot.market == market, QuoteSnapshot.change_pct > 0)
        )
        dec = await session.scalar(
            select(func.count()).where(QuoteSnapshot.market == market, QuoteSnapshot.change_pct < 0)
        )
        key = str(summary.date)
        if await already_fired(
            session,
            market,
            market_wrap.MARKET_CODE,
            "market_wrap",
            key,
            today=summary.date,
            cooldown_days=1,
        ):
            return {"published": 0}
        await publish_note(
            session,
            tenant_id=tenant_id,
            market=market,
            code=market_wrap.MARKET_CODE,
            agent_id=agent_id,
            agent_handle=AGENTS[market_wrap.BEAT][0],
            event_type="market_wrap",
            occurrence_key=key,
            body_i18n={
                "bn": market_wrap.render(summary, adv or 0, dec or 0, "bn"),
                "en": market_wrap.render(summary, adv or 0, dec or 0, "en"),
            },
            as_of=summary.date,
            add_cashtag=False,
        )
        await session.commit()
    return {"published": 1}


async def _run(market: str) -> None:
    lv = await run_levels_agent(market)
    ow = await run_ownership_agents(market)
    vo = await run_volume_agent(market)
    fa = await run_factor_agents(market)
    mk = await run_market_update(market)
    print(
        f"[signals] {market}: levels={lv['published']} ownership={ow['published']} "
        f"volume={vo['published']} factors={fa['published']} market={mk['published']}"
    )


def main() -> None:
    asyncio.run(_run(sys.argv[1] if len(sys.argv) > 1 else "DSE"))


if __name__ == "__main__":
    main()
