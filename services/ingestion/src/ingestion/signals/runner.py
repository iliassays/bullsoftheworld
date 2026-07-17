"""Run the levels-agent over the universe: detect → dedupe → publish notes into stock feeds.

    uv run python -m ingestion.signals.runner DSE bullsofdhaka   # one-shot

Detection re-derives yesterday from the bars, so it's safe to re-run — the signal_events ledger
(unique per occurrence) plus a per-event cooldown stop duplicate or repetitive notes.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import sys

from sqlalchemy import func, or_, select

from bulls.analytics import adjust_bars, compute
from bulls.analytics.indicators import index_change_pct
from bulls.core.db import get_sessionmaker
from bulls.core.institutional_watch import WATCHED_MANAGER_CIKS
from bulls.core.markets import get_market_profile
from bulls.core.models import (
    DailyBar,
    InstitutionalHoldingSummary,
    InstitutionalPosition,
    MarketSummary,
    QuoteSnapshot,
    SecFiling,
    ShareholdingSnapshot,
    ShortVolumeDaily,
    Symbol,
    TickerAnalytics,
)
from bulls.market_data.calendar import to_market_tz
from ingestion.signals import factors, institutional, ownership, sec_filings, shorts, volume
from ingestion.signals import market as market_wrap
from ingestion.signals.agents import agent_identity, ensure_agents
from ingestion.signals.confirmation import SignalConfirmationStore, state_is_confirmed
from ingestion.signals.levels import BEAT, detect, render
from ingestion.signals.publish import already_fired, publish_note

_LOOKBACK = 260
_COOLDOWN_DAYS = 5  # don't repeat the same event on a name within this many days
_OWN_COOLDOWN_DAYS = 20  # ownership discloses monthly — don't refire within a disclosure window


async def run_levels_agent(market: str, *, tenant_id: str) -> dict[str, int]:
    sm = get_sessionmaker()
    handle = agent_identity(tenant_id, BEAT)[0]
    published = 0
    currency = get_market_profile(market).currency_symbol

    async with sm() as session:
        agent_id = (await ensure_agents(session, tenant_id))[BEAT]
        codes = list(
            await session.scalars(
                select(Symbol.code).where(
                    Symbol.market == market,
                    Symbol.is_active.is_(True),
                    Symbol.is_hidden.is_(False),
                    Symbol.data_status == "ready",
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
            asc = adjust_bars(list(reversed(bars)))
            today = compute(asc)
            prev = compute(asc[:-1])

            for sig in detect(prev, today):
                if await already_fired(
                    session,
                    market,
                    code,
                    sig.event_type,
                    sig.occurrence_key,
                    tenant_id=tenant_id,
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
                    body_i18n={
                        "bn": render(sig, code, "bn", currency),
                        "en": render(sig, code, "en", currency),
                    },
                    as_of=today.as_of_date,
                )
                published += 1
        await session.commit()

    return {"symbols": len(codes), "published": published}


async def run_ownership_agents(market: str, *, tenant_id: str) -> dict[str, int]:
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
                    tenant_id=tenant_id,
                    today=latest.as_of_date,
                    cooldown_days=_OWN_COOLDOWN_DAYS,
                ):
                    continue
                handle = agent_identity(tenant_id, sig.beat)[0]
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


async def run_volume_agent(
    market: str,
    *,
    tenant_id: str,
    confirmation_store: SignalConfirmationStore | None = None,
    required_observations: int = 1,
) -> dict[str, int]:
    """Flag persistent unusual intraday volume versus expected-by-now pace.

    Production supplies Redis and requires two distinct delayed snapshots. One-shot maintenance
    calls retain the historical single-observation behavior unless they opt into confirmation.
    The durable signal ledger still guarantees at most one publication per ticker and session.
    """
    now = dt.datetime.now(dt.UTC)
    fraction = volume.session_fraction(now)
    today = to_market_tz(now).date()
    day = str(today)
    sm = get_sessionmaker()
    published = 0
    awaiting_confirmation = 0
    async with sm() as session:
        agent_id = (await ensure_agents(session, tenant_id))[volume.BEAT]
        handle = agent_identity(tenant_id, volume.BEAT)[0]
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
                tenant_id=tenant_id,
                today=today,
                cooldown_days=1,
            ):
                continue
            if confirmation_store is not None and not await state_is_confirmed(
                confirmation_store,
                key=(
                    f"signals:confirm:v1:{tenant_id}:{market}:{code}:"
                    f"{sig.event_type}:{today.isoformat()}"
                ),
                observed_at=as_of.astimezone(dt.UTC).isoformat(),
                state=str(sig.payload.get("direction", "flat")),
                required_observations=required_observations,
            ):
                awaiting_confirmation += 1
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
    return {"published": published, "awaiting_confirmation": awaiting_confirmation}


async def run_eod_volume_agent(market: str, *, tenant_id: str) -> dict[str, int]:
    """Evaluate full-session volume after an EOD snapshot has been published.

    This is deliberately separate from the intraday pace calculation. EOD-only markets compare
    the completed session with the full 20-session average and never imply live monitoring.
    """
    sm = get_sessionmaker()
    published = 0
    async with sm() as session:
        latest_as_of = await session.scalar(
            select(func.max(QuoteSnapshot.as_of)).where(QuoteSnapshot.market == market)
        )
        if latest_as_of is None:
            return {"published": 0}
        day = to_market_tz(latest_as_of, market=market).date()
        day_key = str(day)
        agent_id = (await ensure_agents(session, tenant_id))[volume.BEAT]
        handle = agent_identity(tenant_id, volume.BEAT)[0]
        rows = (
            await session.execute(
                select(
                    QuoteSnapshot.code,
                    QuoteSnapshot.volume,
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
                    QuoteSnapshot.as_of == latest_as_of,
                    Symbol.is_active.is_(True),
                    Symbol.is_hidden.is_(False),
                    Symbol.data_status == "ready",
                )
            )
        ).all()
        for code, session_volume, average_volume, change_pct in rows:
            sig = volume.detect(session_volume, average_volume, 1.0, day_key, change_pct)
            if sig is None or await already_fired(
                session,
                market,
                code,
                sig.event_type,
                sig.occurrence_key,
                tenant_id=tenant_id,
                today=day,
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
                body_i18n={"en": volume.render(sig, code, "en")},
                as_of=day,
            )
            published += 1
        await session.commit()
    return {"published": published}


async def run_short_flow_agent(market: str, *, tenant_id: str) -> dict[str, int]:
    """Descriptive notes when a stock's FINRA short-sale share runs well above its own norm.

    Reads the latest ingested Reg SHO session (never the calendar day — FINRA publishes in the
    evening and skips holidays), compares each ready symbol against its trailing 20-session norm,
    and posts at most a handful of the largest deviations. No data → quietly does nothing.
    """
    if market != "US":
        return {"published": 0}
    sm = get_sessionmaker()
    published = 0
    async with sm() as session:
        latest = await session.scalar(
            select(func.max(ShortVolumeDaily.date)).where(ShortVolumeDaily.market == market)
        )
        if latest is None:
            return {"published": 0}
        day_key = str(latest)
        baseline_cutoff = latest - dt.timedelta(days=30)  # ~20 trading sessions
        agent_id = (await ensure_agents(session, tenant_id))[shorts.BEAT]
        handle = agent_identity(tenant_id, shorts.BEAT)[0]

        baseline = (
            select(
                ShortVolumeDaily.code,
                func.avg(
                    ShortVolumeDaily.short_volume * 1.0 / ShortVolumeDaily.total_volume
                ).label("avg_ratio"),
                func.stddev_samp(
                    ShortVolumeDaily.short_volume * 1.0 / ShortVolumeDaily.total_volume
                ).label("ratio_stddev"),
                func.avg(ShortVolumeDaily.total_volume).label("avg_total_volume"),
                func.count().label("sessions"),
            )
            .where(
                ShortVolumeDaily.market == market,
                ShortVolumeDaily.date >= baseline_cutoff,
                ShortVolumeDaily.date < latest,
                ShortVolumeDaily.total_volume > 0,
            )
            .group_by(ShortVolumeDaily.code)
            .subquery()
        )
        rows = (
            await session.execute(
                select(
                    ShortVolumeDaily.code,
                    ShortVolumeDaily.short_volume.label("short_marked_volume"),
                    ShortVolumeDaily.total_volume,
                    baseline.c.avg_ratio,
                    baseline.c.ratio_stddev,
                    baseline.c.avg_total_volume,
                    baseline.c.sessions,
                )
                .join(baseline, baseline.c.code == ShortVolumeDaily.code)
                .join(
                    Symbol,
                    (Symbol.market == ShortVolumeDaily.market)
                    & (Symbol.code == ShortVolumeDaily.code),
                )
                .where(
                    ShortVolumeDaily.market == market,
                    ShortVolumeDaily.date == latest,
                    Symbol.is_active.is_(True),
                    Symbol.is_hidden.is_(False),
                    Symbol.data_status == "ready",
                )
            )
        ).all()

        signals = []
        for code, short_vol, total_vol, avg_ratio, ratio_stddev, avg_total, sessions in rows:
            sig = shorts.detect(
                float(short_vol),
                float(total_vol),
                float(avg_ratio),
                float(ratio_stddev) if ratio_stddev is not None else None,
                float(avg_total) if avg_total is not None else None,
                int(sessions),
                day_key,
            )
            if sig is not None:
                signals.append((code, sig))
        # Largest deviations first; hard cap keeps the beat scannable, never a flood.
        signals.sort(key=lambda item: item[1].ratio - item[1].avg_ratio, reverse=True)

        for code, sig in signals[: shorts.MAX_NOTES_PER_DAY]:
            if await already_fired(
                session,
                market,
                code,
                sig.event_type,
                sig.occurrence_key,
                tenant_id=tenant_id,
                today=latest,
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
                body_i18n={"en": shorts.render(sig, code)},
                as_of=latest,
            )
            published += 1
        await session.commit()
    return {"published": published}


async def run_us_institutional_agent(*, tenant_id: str) -> dict[str, int]:
    """Publish only material, multi-confirmed changes from the latest Form 13F quarter."""
    sm = get_sessionmaker()
    published = 0
    async with sm() as session:
        ids = await ensure_agents(session, tenant_id)
        summaries = list(
            await session.scalars(
                select(InstitutionalHoldingSummary)
                .join(
                    Symbol,
                    (Symbol.market == InstitutionalHoldingSummary.market)
                    & (Symbol.code == InstitutionalHoldingSummary.code),
                )
                .where(
                    InstitutionalHoldingSummary.market == "US",
                    Symbol.is_active.is_(True),
                    Symbol.is_hidden.is_(False),
                    Symbol.data_status == "ready",
                )
                .order_by(
                    InstitutionalHoldingSummary.code,
                    InstitutionalHoldingSummary.report_date.desc(),
                )
            )
        )
        latest_by_code: dict[str, InstitutionalHoldingSummary] = {}
        for summary in summaries:
            latest_by_code.setdefault(summary.code, summary)
        watched_rows = list(
            await session.scalars(
                select(InstitutionalPosition).where(
                    InstitutionalPosition.market == "US",
                    InstitutionalPosition.manager_cik.in_(WATCHED_MANAGER_CIKS),
                )
            )
        )
        watched_by_key: dict[tuple[str, dt.date], list[str]] = {}
        for row in watched_rows:
            watched_by_key.setdefault((row.code, row.report_date), []).append(row.manager_name)

        signals = []
        for code, row in latest_by_code.items():
            signal = institutional.detect(
                report_date=row.report_date,
                public_by=row.latest_filing_date,
                managers_count=row.managers_count,
                net_change_pct=row.net_change_pct,
                new_positions=row.new_positions,
                increased_positions=row.increased_positions,
                reduced_positions=row.reduced_positions,
                exited_positions=row.exited_positions,
                unchanged_positions=row.unchanged_positions,
                watched_managers=tuple(
                    sorted(set(watched_by_key.get((code, row.report_date), [])))
                ),
            )
            if signal is not None:
                signals.append((code, signal))
        signals.sort(key=lambda item: item[1].rank, reverse=True)

        handle = agent_identity(tenant_id, institutional.BEAT)[0]
        for code, signal in signals[: institutional.MAX_NOTES_PER_RUN]:
            if await already_fired(
                session,
                "US",
                code,
                signal.event_type,
                signal.occurrence_key,
                tenant_id=tenant_id,
                today=signal.public_by,
                cooldown_days=30,
            ):
                continue
            await publish_note(
                session,
                tenant_id=tenant_id,
                market="US",
                code=code,
                agent_id=ids[institutional.BEAT],
                agent_handle=handle,
                event_type=signal.event_type,
                occurrence_key=signal.occurrence_key,
                body_i18n={"en": institutional.render(signal, code)},
                as_of=signal.public_by,
            )
            published += 1
        await session.commit()
    return {"symbols": len(latest_by_code), "qualified": len(signals), "published": published}


async def run_sec_filing_agents(*, tenant_id: str) -> dict[str, int]:
    """Publish recent material EDGAR events without replaying historical onboarding data."""
    since = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=sec_filings.RECENT_DAYS)
    sm = get_sessionmaker()
    published = 0
    async with sm() as session:
        ids = await ensure_agents(session, tenant_id)
        filings = list(
            await session.scalars(
                select(SecFiling)
                .join(
                    Symbol,
                    (Symbol.market == SecFiling.market) & (Symbol.code == SecFiling.code),
                )
                .where(
                    SecFiling.market == "US",
                    SecFiling.filing_date >= since,
                    Symbol.is_active.is_(True),
                    Symbol.is_hidden.is_(False),
                    Symbol.data_status == "ready",
                )
                .order_by(SecFiling.filing_date.desc(), SecFiling.accepted_at.desc())
            )
        )
        qualified = [(row, sec_filings.beat_for(row)) for row in filings]
        qualified = [(row, beat) for row, beat in qualified if beat is not None]
        for filing, beat in qualified[: sec_filings.MAX_NOTES_PER_RUN]:
            event_type = f"sec_{filing.category}"
            if await already_fired(
                session,
                "US",
                filing.code,
                event_type,
                filing.accession_number,
                tenant_id=tenant_id,
                today=filing.filing_date,
                cooldown_days=1,
            ):
                continue
            body = f"{sec_filings.render(filing)} Source: {filing.filing_url}"
            await publish_note(
                session,
                tenant_id=tenant_id,
                market="US",
                code=filing.code,
                agent_id=ids[beat],
                agent_handle=agent_identity(tenant_id, beat)[0],
                event_type=event_type,
                occurrence_key=filing.accession_number,
                body_i18n={"en": body},
                as_of=filing.filing_date,
            )
            published += 1
        await session.commit()
    return {"filings": len(filings), "qualified": len(qualified), "published": published}


async def run_factor_agents(market: str, *, tenant_id: str) -> dict[str, int]:
    """Descriptive factor notes (momentum / quality-value / smart-money / relative strength) from the
    precomputed analytics row + today's price vs the index. Once per name per factor per month."""
    now = dt.datetime.now(dt.UTC)
    local = to_market_tz(now, market=market).date()
    month_key = local.strftime("%Y-%m")
    day = str(local)
    sm = get_sessionmaker()
    published = 0
    profile = get_market_profile(market)
    async with sm() as session:
        ids = await ensure_agents(session, tenant_id)
        # dsex_change is stored in POINTS (as DSE reports it) — convert to the day's % move
        # before comparing against per-stock change_pct (the "DSEX fell 19.0%" incident).
        idx_row = await session.scalar(
            select(MarketSummary)
            .where(MarketSummary.market == market)
            .order_by(MarketSummary.date.desc())
            .limit(1)
        )
        if idx_row is None:
            benchmark_change_pct = None
        elif market == "DSE":
            benchmark_change_pct = index_change_pct(idx_row.dsex, idx_row.dsex_change)
        elif idx_row.benchmark_close is not None and idx_row.benchmark_change is not None:
            prior_close = idx_row.benchmark_close - idx_row.benchmark_change
            benchmark_change_pct = (
                idx_row.benchmark_change / prior_close * 100 if prior_close > 0 else None
            )
        else:
            benchmark_change_pct = None
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
        candidates: dict[str, list[tuple[TickerAnalytics, factors.FactorSignal]]] = {}
        for ta, change_pct in rows:
            sigs = [
                factors.detect_momentum(ta, month_key),
                factors.detect_quality(ta, month_key),
                factors.detect_accumulation(ta, month_key),
                factors.detect_strength(change_pct, benchmark_change_pct, day),
                factors.detect_breakout(ta, change_pct, day),
            ]
            if market == "DSE":
                sigs.extend(
                    [
                        factors.detect_smartmoney(ta, month_key),
                        # DSE circuit bands are exchange-specific; never apply them to U.S. data.
                        factors.detect_circuit(change_pct, day, ta.last_close),
                    ]
                )
            for sig in sigs:
                if sig is None:
                    continue
                if await already_fired(
                    session,
                    market,
                    ta.code,
                    sig.event_type,
                    sig.occurrence_key,
                    tenant_id=tenant_id,
                    today=ta.as_of_date,
                    cooldown_days=sig.cooldown_days,
                ):
                    continue
                candidates.setdefault(sig.beat, []).append((ta, sig))

        for beat, beat_candidates in candidates.items():
            beat_candidates.sort(key=lambda item: item[1].rank, reverse=True)
            for ta, sig in beat_candidates[: factors.MAX_NOTES_PER_BEAT]:
                await publish_note(
                    session,
                    tenant_id=tenant_id,
                    market=market,
                    code=ta.code,
                    agent_id=ids[beat],
                    agent_handle=agent_identity(tenant_id, beat)[0],
                    event_type=sig.event_type,
                    occurrence_key=sig.occurrence_key,
                    body_i18n={
                        "bn": factors.render(
                            sig,
                            ta.code,
                            "bn",
                            currency=profile.currency_symbol,
                            benchmark=profile.benchmark_label,
                        ),
                        "en": factors.render(
                            sig,
                            ta.code,
                            "en",
                            currency=profile.currency_symbol,
                            benchmark=profile.benchmark_label,
                        ),
                    },
                    as_of=ta.as_of_date,
                )
                published += 1
        await session.commit()
    return {"symbols": len(rows), "published": published}


async def run_market_update(market: str, *, tenant_id: str) -> dict[str, int]:
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
            tenant_id=tenant_id,
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
            agent_handle=agent_identity(tenant_id, market_wrap.BEAT)[0],
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


async def _run(market: str, tenant_id: str) -> None:
    lv = await run_levels_agent(market, tenant_id=tenant_id)
    ow = await run_ownership_agents(market, tenant_id=tenant_id)
    vo = await run_volume_agent(market, tenant_id=tenant_id)
    fa = await run_factor_agents(market, tenant_id=tenant_id)
    mk = await run_market_update(market, tenant_id=tenant_id)
    print(
        f"[signals] {market}: levels={lv['published']} ownership={ow['published']} "
        f"volume={vo['published']} factors={fa['published']} market={mk['published']}"
    )


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python -m ingestion.signals.runner MARKET TENANT_ID")
    asyncio.run(_run(sys.argv[1].upper(), sys.argv[2]))


if __name__ == "__main__":
    main()
