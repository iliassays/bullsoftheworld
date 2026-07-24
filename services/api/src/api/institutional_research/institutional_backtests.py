"""Database adapters for the preregistered US institutional systems.

The analytics package owns signal and portfolio logic. This module only reconstructs market data
as it was knowable, enforces the US boundary, and returns frozen schedules plus readiness evidence
to the Atlas trial workflow.
"""

from __future__ import annotations

import bisect
import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import desc, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.institutional_research.schemas import BacktestRequest
from bulls.analytics.cost_observatory import estimate_spread
from bulls.analytics.factor_sleeve import (
    FundamentalObservation,
    SleevePolicy,
    point_in_time_factor_fundamentals,
)
from bulls.analytics.filing_book import (
    BookPolicy,
    CandidateEvent,
    CandidateMarketState,
    build_weight_schedule,
    rejection_summary,
    screen_candidates,
)
from bulls.analytics.filing_signals import (
    ActivistEvent,
    ActivistRoster,
    InsiderTrade,
    classify_insider,
    detect_clusters,
    has_plausible_transaction_clock,
    qualifying_activist_events,
    qualifying_purchases,
)
from bulls.analytics.forced_seller import (
    ForcedSellerDatasetCoverage,
    assess_forced_seller_readiness,
)
from bulls.analytics.institutional_schedules import build_factor_schedules
from bulls.analytics.research_strategy import (
    ExecutionTiming,
    StrategyBar,
    StrategySecurity,
)
from bulls.core.models import (
    DailyBar,
    EdgarFilingEvent,
    InsiderTransaction,
    OwnershipStakeEvent,
    SecFinancialFactObservation,
    SecurityMaster,
    Symbol,
)
from bulls.market_data.providers.sec_edgar import METRIC_SPECS

_FACTOR_METRICS = ("equity", "net_income", "shares_outstanding")
_ACTIVIST_FRAGMENTS = (
    "elliott",
    "third point",
    "pershing square",
    "valueact",
    "starboard value",
    "icahn",
    "trian",
    "jana partners",
    "corvex",
    "sachem head",
    "engaged capital",
    "legion partners",
    "ancora",
    "politan",
    "engine capital",
    "carl c",
    "value act",
    "scion",
    "cannell",
    "barington",
    "land & buildings",
    "impactive",
    "inclusive capital",
    "sarissa",
)
_CONCEPT_PRIORITY = {
    (spec.metric, concept.taxonomy, concept.concept): priority
    for spec in METRIC_SPECS
    for priority, concept in enumerate(spec.concepts)
}


def _delay_schedule(
    schedule: dict[dt.date, dict[str, float]],
    *,
    sessions: list[dt.date],
    delay_sessions: int,
) -> dict[dt.date, dict[str, float]]:
    """Build a deterministic event-timing placebo without looking backward from a future date."""

    if delay_sessions < 1:
        raise ValueError("placebo delay must be at least one completed session")
    delayed: dict[dt.date, dict[str, float]] = {}
    for as_of, weights in schedule.items():
        index = bisect.bisect_left(sessions, as_of)
        delayed_index = index + delay_sessions
        if index < len(sessions) and sessions[index] == as_of and delayed_index < len(sessions):
            delayed[sessions[delayed_index]] = weights.copy()
    return delayed


@dataclass(frozen=True)
class InstitutionalBacktestPreparation:
    securities: list[StrategySecurity]
    weight_schedule: dict[dt.date, dict[str, float]]
    execution_timing: ExecutionTiming = "next_close"
    comparators: dict[str, dict[dt.date, dict[str, float]]] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    failed_gates: list[str] = field(default_factory=list)
    inactive_security_history_complete: bool = False
    point_in_time_inputs_complete: bool = False


def _adjusted_bar(row) -> StrategyBar | None:
    if min(row.open or 0, row.high or 0, row.low or 0, row.close or 0) <= 0:
        return None
    if row.adjusted_close is not None and row.adjusted_close <= 0:
        return None
    adjustment = (
        row.adjusted_close / row.close if row.adjusted_close is not None and row.close > 0 else 1.0
    )
    return StrategyBar(
        date=row.date,
        open=row.open * adjustment,
        high=row.high * adjustment,
        low=row.low * adjustment,
        close=row.close * adjustment,
        volume=int(row.volume or 0),
    )


async def _bars(
    session: AsyncSession,
    *,
    codes: list[str],
    start: dt.date,
    end: dt.date,
) -> dict[str, list[StrategyBar]]:
    if not codes:
        return {}
    rows = list(
        await session.scalars(
            select(DailyBar)
            .where(
                DailyBar.market == "US",
                DailyBar.code.in_(codes),
                DailyBar.date >= start,
                DailyBar.date <= end,
            )
            .order_by(DailyBar.code, DailyBar.date)
        )
    )
    grouped: dict[str, list[StrategyBar]] = defaultdict(list)
    invalid_codes: set[str] = set()
    for row in rows:
        bar = _adjusted_bar(row)
        if bar is None:
            invalid_codes.add(row.code)
            continue
        grouped[row.code].append(bar)
    for code in invalid_codes:
        grouped.pop(code, None)
    return dict(grouped)


async def _securities(
    session: AsyncSession,
    bars: dict[str, list[StrategyBar]],
    *,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> list[StrategySecurity]:
    if not bars:
        return []
    symbols = {
        symbol.code: symbol
        for symbol in await session.scalars(
            select(Symbol).where(Symbol.market == "US", Symbol.code.in_(list(bars)))
        )
    }
    return [
        StrategySecurity(
            code=code,
            sector=(symbols.get(code).sector if symbols.get(code) else None) or "Unclassified",
            cap_tier="unclassified",
            bars=[
                bar
                for bar in history
                if (start is None or bar.date >= start) and (end is None or bar.date <= end)
            ],
        )
        for code, history in sorted(bars.items())
        if any(
            (start is None or bar.date >= start) and (end is None or bar.date <= end)
            for bar in history
        )
    ]


async def _fundamental_observations(
    session: AsyncSession,
    *,
    codes: list[str],
    end: dt.date,
    metrics: tuple[str, ...] = _FACTOR_METRICS,
) -> list[FundamentalObservation]:
    if not codes:
        return []
    cutoff = dt.datetime.combine(end, dt.time.max, tzinfo=dt.UTC)
    rows = (
        await session.execute(
            select(
                SecFinancialFactObservation.code,
                SecFinancialFactObservation.metric,
                SecFinancialFactObservation.value,
                SecFinancialFactObservation.unit,
                SecFinancialFactObservation.period_start,
                SecFinancialFactObservation.period_end,
                SecFinancialFactObservation.period_type,
                SecFinancialFactObservation.known_at,
                SecFinancialFactObservation.accession_number,
                SecFinancialFactObservation.taxonomy,
                SecFinancialFactObservation.source_concept,
            ).where(
                SecFinancialFactObservation.market == "US",
                SecFinancialFactObservation.code.in_(codes),
                SecFinancialFactObservation.metric.in_(metrics),
                SecFinancialFactObservation.known_at <= cutoff,
            )
        )
    ).all()
    return [
        FundamentalObservation(
            code=row.code,
            metric=row.metric,
            value=row.value,
            unit=row.unit,
            period_start=row.period_start,
            period_end=row.period_end,
            period_type=row.period_type,
            known_at=row.known_at,
            accession_number=row.accession_number,
            concept_priority=_CONCEPT_PRIORITY.get(
                (row.metric, row.taxonomy, row.source_concept),
                len(METRIC_SPECS),
            ),
        )
        for row in rows
    ]


async def _factor_preparation(
    session: AsyncSession,
    *,
    request: BacktestRequest,
    start: dt.date,
    end: dt.date,
) -> InstitutionalBacktestPreparation:
    failed_gates: list[str] = []
    if request.codes:
        codes = sorted({code.upper() for code in request.codes})
        failed_gates.append(
            "A user-selected symbol subset is diagnostic and cannot establish cross-sectional evidence."
        )
    else:
        liquidity = (
            select(
                DailyBar.code,
                func.avg(DailyBar.close * DailyBar.volume).label("average_dollar_volume"),
            )
            .join(
                SecurityMaster,
                (SecurityMaster.market == DailyBar.market)
                & (SecurityMaster.symbol == DailyBar.code),
            )
            .where(
                DailyBar.market == "US",
                SecurityMaster.instrument_type.in_(("common_stock", "adr")),
                DailyBar.date < start,
                DailyBar.date >= start - dt.timedelta(days=180),
            )
            .group_by(DailyBar.code)
            .order_by(desc("average_dollar_volume"), DailyBar.code)
            .limit(request.universe_limit)
        )
        codes = [code for code, _ in (await session.execute(liquidity)).all()]
        failed_gates.append(
            "The interactive universe is liquidity-ranked and capped; promotion requires the uncapped historical universe."
        )
    failed_gates.append(
        "Historical capitalization-tier membership is incomplete; small-cap tier robustness cannot be reported."
    )
    if request.cap_tier:
        failed_gates.append(
            "The requested capitalization tier uses current metadata and cannot be projected backward."
        )
    bars = await _bars(
        session,
        codes=codes,
        start=start - dt.timedelta(days=400),
        end=end,
    )
    observations = await _fundamental_observations(
        session,
        codes=list(bars),
        end=end,
    )
    sessions = sorted(
        {bar.date for history in bars.values() for bar in history if start <= bar.date <= end}
    )
    bundle = build_factor_schedules(
        bars=bars,
        observations=observations,
        sessions=sessions,
        policy=SleevePolicy(target_positions=40, minimum_factors=4),
        max_half_spread_bps=50.0,
    )
    if not bundle.strategy:
        failed_gates.append(
            "No monthly rebalance had 252 sessions plus all four point-in-time factor inputs."
        )
    return InstitutionalBacktestPreparation(
        securities=await _securities(session, bars, start=start, end=end),
        weight_schedule=bundle.strategy,
        comparators={
            "equal_weight_eligible_universe": bundle.equal_weight_null,
            "naive_momentum": bundle.momentum_null,
            "cap_weighted_eligible_universe": bundle.cap_weighted_null,
        },
        diagnostics={
            **bundle.diagnostics,
            "selection": "pre-start trailing dollar volume",
            "requested_universe_limit": request.universe_limit,
            "fundamental_observations": len(observations),
        },
        failed_gates=failed_gates,
        point_in_time_inputs_complete=True,
    )


def _session_for_signal(
    signal_at: dt.datetime,
    session_dates: list[dt.date],
) -> dt.datetime | None:
    index = bisect.bisect_left(session_dates, signal_at.date())
    if index >= len(session_dates):
        return None
    return dt.datetime.combine(session_dates[index], dt.time.max, tzinfo=dt.UTC)


def _spread_as_of(
    symbol: str,
    as_of: dt.date,
    bars: dict[str, list[StrategyBar]],
) -> float | None:
    completed = [bar for bar in bars.get(symbol, []) if bar.date <= as_of][-60:]
    estimate = estimate_spread(
        symbol,
        [bar.high for bar in completed],
        [bar.low for bar in completed],
    )
    return estimate.half_spread_bps if estimate is not None else None


def _candidate_state(
    symbol: str,
    *,
    as_of: dt.date,
    bars: dict[str, list[StrategyBar]],
    shares: dict[str, dict[str, float]],
) -> CandidateMarketState:
    close = next(
        (bar.close for bar in reversed(bars.get(symbol, [])) if bar.date <= as_of),
        None,
    )
    share_count = shares.get(symbol, {}).get("shares_outstanding")
    return CandidateMarketState(
        half_spread_bps=_spread_as_of(symbol, as_of, bars),
        short_interest_pct_of_float=None,
        market_cap_mn=(close * share_count / 1_000_000 if close and share_count else None),
    )


async def _event_candidates(
    session: AsyncSession,
    *,
    strategy_key: str,
    start: dt.date,
    end: dt.date,
) -> tuple[list[CandidateEvent], list[Any], list[Any], list[Any], int]:
    master_rows = (
        await session.execute(
            select(SecurityMaster.cik, SecurityMaster.symbol).where(
                SecurityMaster.market == "US",
                SecurityMaster.cik.is_not(None),
            )
        )
    ).all()
    bridge_rows = (
        await session.execute(
            select(distinct(InsiderTransaction.issuer_cik), InsiderTransaction.issuer_symbol).where(
                InsiderTransaction.issuer_symbol.is_not(None)
            )
        )
    ).all()
    stake_rows = (
        await session.execute(
            select(
                OwnershipStakeEvent.accession_number,
                OwnershipStakeEvent.subject_cik,
                OwnershipStakeEvent.subject_name,
                OwnershipStakeEvent.filed_by_cik,
                OwnershipStakeEvent.filed_by_name,
                OwnershipStakeEvent.form,
                OwnershipStakeEvent.accepted_at,
                OwnershipStakeEvent.percent_of_class,
            ).where(
                OwnershipStakeEvent.form.like("%13%"),
                OwnershipStakeEvent.accepted_at.is_not(None),
                OwnershipStakeEvent.accepted_at
                >= dt.datetime.combine(start, dt.time.min, tzinfo=dt.UTC),
                OwnershipStakeEvent.accepted_at
                <= dt.datetime.combine(end, dt.time.max, tzinfo=dt.UTC),
            )
        )
    ).all()
    if strategy_key == "us_activist_13d_v1":
        cik_to_symbol = {cik: symbol for cik, symbol in bridge_rows if symbol}
        cik_to_symbol.update({cik: symbol for cik, symbol in master_rows if symbol})
        roster = ActivistRoster(name_fragments=_ACTIVIST_FRAGMENTS)
        events = [
            ActivistEvent(
                accession_number=row.accession_number,
                subject_cik=row.subject_cik,
                subject_name=row.subject_name,
                filed_by_cik=row.filed_by_cik,
                filed_by_name=row.filed_by_name,
                form=row.form,
                signal_at=row.accepted_at,
                percent_of_class=row.percent_of_class,
                is_amendment="/A" in (row.form or ""),
            )
            for row in stake_rows
            if "13D" in (row.form or "").upper()
        ]
        candidates = [
            CandidateEvent(
                symbol=cik_to_symbol[event.subject_cik],
                issuer_cik=event.subject_cik,
                kind="activist_13d",
                signal_at=event.signal_at,
                strength=5.0,
            )
            for event in qualifying_activist_events(events, roster)
            if event.subject_cik in cik_to_symbol
        ]
        return candidates, stake_rows, master_rows, bridge_rows, 0

    purchase_rows = (
        await session.execute(
            select(
                InsiderTransaction.issuer_cik,
                InsiderTransaction.issuer_symbol,
                InsiderTransaction.owner_cik,
                InsiderTransaction.transaction_date,
                InsiderTransaction.code,
                InsiderTransaction.shares,
                InsiderTransaction.price_per_share,
                InsiderTransaction.is_10b5_1_plan,
                InsiderTransaction.is_officer,
                InsiderTransaction.is_director,
                InsiderTransaction.is_ten_percent_owner,
                EdgarFilingEvent.accepted_at,
            )
            .join(
                EdgarFilingEvent,
                EdgarFilingEvent.accession_number == InsiderTransaction.accession_number,
            )
            .where(
                InsiderTransaction.code == "P",
                InsiderTransaction.transaction_date.is_not(None),
                # Guard against residual impossible Form 4 dates that predate the
                # ingestion-time rejection (commit 82cdd8e); 32 such rows remain in prod.
                InsiderTransaction.transaction_date >= dt.date(1990, 1, 1),
                InsiderTransaction.transaction_date <= dt.date(2030, 12, 31),
                EdgarFilingEvent.accepted_at.is_not(None),
                EdgarFilingEvent.accepted_at
                >= dt.datetime.combine(start, dt.time.min, tzinfo=dt.UTC) - dt.timedelta(days=45),
                EdgarFilingEvent.accepted_at
                <= dt.datetime.combine(end, dt.time.max, tzinfo=dt.UTC),
            )
        )
    ).all()
    owners = sorted({row.owner_cik for row in purchase_rows})
    history_rows = []
    if owners:
        history_rows = (
            await session.execute(
                select(
                    InsiderTransaction.owner_cik,
                    InsiderTransaction.transaction_date,
                    EdgarFilingEvent.accepted_at,
                )
                .join(
                    EdgarFilingEvent,
                    EdgarFilingEvent.accession_number == InsiderTransaction.accession_number,
                )
                .where(
                    InsiderTransaction.owner_cik.in_(owners),
                    InsiderTransaction.transaction_date.is_not(None),
                    # Guard against residual impossible Form 4 dates that predate the
                    # ingestion-time rejection (commit 82cdd8e); 32 such rows remain in prod.
                    InsiderTransaction.transaction_date >= dt.date(1990, 1, 1),
                    InsiderTransaction.transaction_date <= dt.date(2030, 12, 31),
                    EdgarFilingEvent.accepted_at.is_not(None),
                    EdgarFilingEvent.accepted_at
                    <= dt.datetime.combine(end, dt.time.max, tzinfo=dt.UTC),
                )
                .order_by(InsiderTransaction.owner_cik, EdgarFilingEvent.accepted_at)
            )
        ).all()
    invalid_transaction_clocks = sum(
        not has_plausible_transaction_clock(transaction_date, accepted_at)
        for _, transaction_date, accepted_at in history_rows
    )
    history_rows = [
        row
        for row in history_rows
        if has_plausible_transaction_clock(row.transaction_date, row.accepted_at)
    ]
    purchase_rows = [
        row
        for row in purchase_rows
        if has_plausible_transaction_clock(row.transaction_date, row.accepted_at)
    ]
    owner_history: dict[int, list[tuple[dt.datetime, dt.date]]] = defaultdict(list)
    for owner_cik, transaction_date, accepted_at in history_rows:
        owner_history[owner_cik].append((accepted_at, transaction_date))
    purchases: list[InsiderTrade] = []
    for row in purchase_rows:
        trade = InsiderTrade(
            issuer_cik=row.issuer_cik,
            issuer_symbol=row.issuer_symbol,
            owner_cik=row.owner_cik,
            transaction_date=row.transaction_date,
            disseminated_at=row.accepted_at,
            code=row.code,
            shares=row.shares,
            price_per_share=row.price_per_share,
            is_10b5_1_plan=row.is_10b5_1_plan,
            is_officer=row.is_officer,
            is_director=row.is_director,
            is_ten_percent_owner=row.is_ten_percent_owner,
        )
        history = owner_history.get(trade.owner_cik, [])
        cut = bisect.bisect_right(
            [known_at for known_at, _ in history],
            trade.disseminated_at,
        )
        classification = classify_insider([date for _, date in history[:cut]])
        purchases.extend(qualifying_purchases([trade], {trade.owner_cik: classification}))
    clusters = detect_clusters(
        [trade for trade in purchases if trade.issuer_symbol],
        window_days=30,
        minimum_insiders=1,
    )
    candidates = [
        CandidateEvent(
            symbol=cluster.issuer_symbol,
            issuer_cik=cluster.issuer_cik,
            kind="insider_cluster",
            signal_at=cluster.signal_at,
            strength=cluster.distinct_insiders
            + (0.5 if cluster.includes_officer_or_director else 0.0),
        )
        for cluster in clusters
        if cluster.issuer_symbol and cluster.signal_at.date() >= start
    ]
    return (
        candidates,
        stake_rows,
        master_rows,
        bridge_rows,
        invalid_transaction_clocks,
    )


def _thesis_breaks(
    stake_rows: list[Any],
    *,
    master_rows: list[Any],
    bridge_rows: list[Any],
    session_dates: list[dt.date],
) -> dict[dt.datetime, dict[str, str]]:
    cik_to_symbol = {cik: symbol for cik, symbol in bridge_rows if symbol}
    cik_to_symbol.update({cik: symbol for cik, symbol in master_rows if symbol})
    roster = ActivistRoster(name_fragments=_ACTIVIST_FRAGMENTS)
    breaks: dict[dt.datetime, dict[str, str]] = defaultdict(dict)
    for row in stake_rows:
        if row.subject_cik not in cik_to_symbol or not roster.matches(
            cik=row.filed_by_cik, name=row.filed_by_name
        ):
            continue
        form = (row.form or "").upper()
        reason = None
        if "13G" in form:
            reason = "converted_to_13g"
        elif "13D/A" in form and row.percent_of_class is not None and row.percent_of_class <= 0.5:
            reason = "stake_exit"
        if reason is None:
            continue
        session_at = _session_for_signal(row.accepted_at, session_dates)
        if session_at is not None:
            breaks[session_at][cik_to_symbol[row.subject_cik]] = reason
    return dict(breaks)


async def _event_preparation(
    session: AsyncSession,
    *,
    strategy_key: str,
    request: BacktestRequest,
    start: dt.date,
    end: dt.date,
) -> InstitutionalBacktestPreparation:
    (
        candidates,
        stake_rows,
        master_rows,
        bridge_rows,
        invalid_transaction_clocks,
    ) = await _event_candidates(
        session,
        strategy_key=strategy_key,
        start=start,
        end=end,
    )
    if request.codes:
        requested = {code.upper() for code in request.codes}
        candidates = [candidate for candidate in candidates if candidate.symbol in requested]
    codes = sorted({candidate.symbol for candidate in candidates})
    bars = await _bars(
        session,
        codes=codes,
        start=start - dt.timedelta(days=400),
        end=end,
    )
    observations = await _fundamental_observations(
        session,
        codes=list(bars),
        end=end,
        metrics=("shares_outstanding",),
    )
    session_dates = sorted(
        {bar.date for history in bars.values() for bar in history if start <= bar.date <= end}
    )
    sessions = [dt.datetime.combine(date, dt.time.max, tzinfo=dt.UTC) for date in session_dates]
    by_session: dict[dt.datetime, list[CandidateEvent]] = defaultdict(list)
    for candidate in candidates:
        session_at = _session_for_signal(candidate.signal_at, session_dates)
        if session_at is not None:
            by_session[session_at].append(candidate)
    state_by_session: dict[dt.datetime, dict[str, CandidateMarketState]] = {}
    all_screened = []
    policy = BookPolicy(
        max_position_pct=0.05,
        max_concurrent_positions=20,
        max_half_spread_bps=100.0,
        minimum_market_cap_mn=100.0,
        time_stop_days=365,
        screen_crowding=False,
        require_market_cap=False,
    )
    for session_at, session_candidates in by_session.items():
        shares = point_in_time_factor_fundamentals(
            observations,
            as_of=session_at,
        )
        state = {
            candidate.symbol: _candidate_state(
                candidate.symbol,
                as_of=session_at.date(),
                bars=bars,
                shares=shares,
            )
            for candidate in session_candidates
        }
        state_by_session[session_at] = state
        all_screened.extend(screen_candidates(session_candidates, state, policy))
    schedule_dt, advances = build_weight_schedule(
        sessions=sessions,
        candidates_by_session=by_session,
        market_state_by_session=state_by_session,
        policy=policy,
        thesis_breaks_by_session=(
            _thesis_breaks(
                stake_rows,
                master_rows=master_rows,
                bridge_rows=bridge_rows,
                session_dates=session_dates,
            )
            if strategy_key == "us_activist_13d_v1"
            else None
        ),
        emit_unchanged=False,
    )
    schedule = {timestamp.date(): weights for timestamp, weights in schedule_dt.items()}
    failed_gates = [
        "Inactive and acquired target history has not yet passed a complete listing-history audit.",
        "Short-interest-as-percent-of-float is unavailable, so the preregistered crowding gate is disabled.",
        "Historical capitalization-tier membership is incomplete; event results cannot be split by contemporaneous size tier.",
    ]
    if request.codes:
        failed_gates.append(
            "A user-selected event subset is diagnostic and cannot establish event-family evidence."
        )
    if not schedule:
        failed_gates.append("No event cleared the point-in-time tradeability gates in this window.")
    delayed_placebo = _delay_schedule(
        schedule,
        sessions=session_dates,
        delay_sessions=21,
    )
    if schedule and not delayed_placebo:
        failed_gates.append(
            "The 21-session event-timing placebo has no executable delayed observations."
        )
    return InstitutionalBacktestPreparation(
        securities=await _securities(session, bars, start=start, end=end),
        weight_schedule=schedule,
        comparators={"event_timing_plus_21_sessions": delayed_placebo},
        diagnostics={
            "candidate_events": len(candidates),
            "schedule_changes": len(schedule),
            "book_sessions": len(advances),
            "rejections": rejection_summary(all_screened),
            "crowding_screen": "disabled_missing_short_interest_pct_of_float",
            "fundamental_observations": len(observations),
            "event_timing_placebo_delay_sessions": 21,
            "invalid_transaction_clocks_rejected": invalid_transaction_clocks,
        },
        failed_gates=failed_gates,
    )


async def prepare_institutional_backtest(
    session: AsyncSession,
    *,
    strategy_key: str,
    request: BacktestRequest,
) -> InstitutionalBacktestPreparation:
    if strategy_key not in {
        "us_activist_13d_v1",
        "us_insider_cluster_v1",
        "us_forced_seller_v1",
        "us_factor_sleeve_v1",
    }:
        raise ValueError(f"{strategy_key} is not an institutional system")
    end = request.end_date or await session.scalar(
        select(func.max(DailyBar.date)).where(DailyBar.market == "US")
    )
    if end is None:
        return InstitutionalBacktestPreparation(
            securities=[],
            weight_schedule={},
            failed_gates=["No completed US daily-bar history is available."],
        )
    start = request.start_date or end - dt.timedelta(days=365 * 3 + 30)
    if start >= end:
        raise ValueError("start_date must be earlier than end_date")
    if strategy_key == "us_factor_sleeve_v1":
        return await _factor_preparation(
            session,
            request=request,
            start=start,
            end=end,
        )
    if strategy_key in {"us_activist_13d_v1", "us_insider_cluster_v1"}:
        return await _event_preparation(
            session,
            strategy_key=strategy_key,
            request=request,
            start=start,
            end=end,
        )

    readiness = assess_forced_seller_readiness(ForcedSellerDatasetCoverage())
    return InstitutionalBacktestPreparation(
        securities=[],
        weight_schedule={},
        diagnostics={"readiness": readiness.model_dump(mode="json")},
        failed_gates=[
            f"System B data-blocked: {dataset}" for dataset in readiness.missing_datasets
        ],
    )
