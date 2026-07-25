"""Tenant-bound Atlas decision archive and discovery-performance read model.

The append-only strategy ledger remains authoritative. This module reconstructs what each paper
book knew on a selected completed session, then measures the subsequent price path without
rewriting the archived decision. It never treats the research queue as a buy ranking.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.institutional_research.investment import risk_policy_from_snapshot
from api.institutional_research.schemas import (
    DecisionBoardOut,
    DecisionCandidateOut,
    DecisionCandidatePathOut,
    DecisionDirectionCapabilityOut,
    DecisionEventOut,
    DecisionPricePointOut,
)
from bulls.analytics.research_strategy import RISK_POLICIES, STRATEGIES
from bulls.core.models import (
    CapTierObservation,
    DailyBar,
    ResearchDecisionEvent,
    ResearchShadowPortfolio,
    ResearchShadowSnapshot,
    ResearchWorkspace,
    Symbol,
    TickerAnalytics,
)

DecisionState = Literal["ready", "manage", "exit", "blocked", "closed"]

_STATE_ORDER: dict[DecisionState, int] = {
    "exit": 0,
    "blocked": 1,
    "ready": 2,
    "manage": 3,
    "closed": 4,
}


def direction_capabilities(market: str) -> list[DecisionDirectionCapabilityOut]:
    long_reason = "Registered long strategies have complete execution and portfolio-risk controls."
    if market == "US":
        short_reason = (
            "Short execution is blocked until Atlas has point-in-time borrow availability, locate "
            "outcomes, borrow fees, recall/buy-in handling and short-specific squeeze controls. "
            "FINRA daily short volume is not a substitute for those inputs."
        )
    else:
        short_reason = (
            "The DSE paper engine is cash-equity long-only and has no validated securities-borrow "
            "or short-sale execution workflow."
        )
    return [
        DecisionDirectionCapabilityOut(direction="long", status="active", reason=long_reason),
        DecisionDirectionCapabilityOut(direction="short", status="blocked", reason=short_reason),
    ]


def adjusted_close(bar: DailyBar) -> float:
    return float(bar.adjusted_close if bar.adjusted_close is not None else bar.close)


def adjustment_complete(bars: Sequence[DailyBar]) -> bool:
    """True only when every bar carries an audited adjustment factor.

    DSE bars currently store no adjusted closes at all, so DSE performance is measured on raw
    exchange closes. That must be said, never implied away: a bonus or rights issue shows up as
    a price drop, not as a neutral adjustment.
    """

    return bool(bars) and all(bar.adjusted_close is not None for bar in bars)


def portfolio_stop_loss(portfolio: ResearchShadowPortfolio, market: str) -> float:
    """Resolve the stop the engine actually enforces for this book.

    Each book pins its mandate at inception; the market default is only the fallback for legacy
    configurations. The displayed invalidation price must come from the same policy the engine
    uses, or the archive would show a stop the book never had.
    """

    pinned = portfolio.configuration.get("mandate")
    if isinstance(pinned, dict):
        try:
            return risk_policy_from_snapshot(pinned, market).position_stop_loss
        except (ValueError, TypeError):
            pass
    return RISK_POLICIES[market].position_stop_loss


def price_plan(
    *,
    state: DecisionState,
    as_of_price: float | None,
    average_cost: float | None,
    stop_loss: float,
    reward_risk: float = 2.0,
) -> tuple[float | None, float | None, float | None]:
    """Return the actual stop basis and a non-forecast planning objective.

    The engine enforces its position stop from average cost after a fill. Before a fill, the
    completed-session close is only a planning reference and the values must be recomputed from
    the eventual fill. Exit/closed/blocked states intentionally have no new price plan.
    """

    if state not in {"ready", "manage"}:
        return None, None, None
    reference = average_cost if state == "manage" and average_cost else as_of_price
    if reference is None or reference <= 0 or not 0 < stop_loss < 1 or reward_risk <= 0:
        return None, None, None
    risk_per_share = reference * stop_loss
    return (
        round(reference, 6),
        round(reference - risk_per_share, 6),
        round(reference + reward_risk * risk_per_share, 6),
    )


def _forward_evidence_started_on(portfolio: ResearchShadowPortfolio) -> dt.date:
    raw = portfolio.configuration.get("forward_evidence_started_on")
    if isinstance(raw, str):
        try:
            return dt.date.fromisoformat(raw)
        except ValueError:
            pass
    return portfolio.inception_date


def derive_decision_state(
    *,
    target_weight: float,
    has_position: bool,
    snapshot_events: Sequence[ResearchDecisionEvent],
) -> DecisionState:
    """Resolve one unambiguous action state from the persisted target and execution ledger."""

    if has_position and target_weight <= 0:
        return "exit"
    if has_position:
        return "manage"
    if target_weight > 0:
        if any(event.event_type == "rejection" for event in snapshot_events):
            return "blocked"
        return "ready"
    if any(event.event_type == "rejection" for event in snapshot_events):
        return "blocked"
    return "closed"


def discovery_performance(
    prices: Sequence[float], *, reference_price: float | None
) -> tuple[float | None, float | None, float | None]:
    """Return current, maximum favorable, and maximum adverse percentage moves.

    Close-to-close. Because the first element of ``prices`` is the discovery bar itself, the
    favorable figure can never be below 0 and the adverse figure can never be above it — so an
    adverse reading of exactly 0.00% means only "never *closed* below discovery", which is a much
    weaker statement than "never went against you". Use
    :func:`intraday_excursion` for the traded extremes.
    """

    if reference_price is None or reference_price <= 0 or not prices:
        return None, None, None
    returns = [(price / reference_price - 1) * 100 for price in prices]
    return round(returns[-1], 3), round(max(returns), 3), round(min(returns), 3)


def intraday_excursion(
    highs: Sequence[float], lows: Sequence[float], *, reference_price: float | None
) -> tuple[float | None, float | None]:
    """Peak and trough the price actually *traded* at, as percentages of the discovery price.

    The close-to-close pair understates both sides, sometimes badly: on 2026-07-15 AEHR showed a
    close-based +29.31%/+0.00% while the tape ran +62.32% and -6.73%, the latter touching the
    setup's own invalidation level. Reporting only the close-based pair let 680 of 930
    zero-adverse setups (73%) present as though they had never traded against the reader.

    These are excursions, not achievable returns — nobody exits at the exact high — so they must
    be labelled as the traded range and never summed into a performance claim.
    """

    if reference_price is None or reference_price <= 0 or not highs or not lows:
        return None, None
    peak = (max(highs) / reference_price - 1) * 100
    trough = (min(lows) / reference_price - 1) * 100
    return round(peak, 3), round(trough, 3)


def _event_out(event: ResearchDecisionEvent) -> DecisionEventOut:
    return DecisionEventOut(
        id=event.id,
        portfolio_id=event.portfolio_id,
        snapshot_id=event.snapshot_id,
        correlation_id=event.correlation_id,
        sequence=event.sequence,
        event_key=event.event_key,
        caused_by_event_key=event.caused_by_event_key,
        event_type=event.event_type,
        event_state=event.event_state,
        code=event.code,
        effective_date=event.effective_date,
        payload=event.payload,
        payload_hash=event.payload_hash,
        recorded_at=event.recorded_at,
    )


def _latest_bar_on_or_before(bars: Sequence[DailyBar], value: dt.date) -> DailyBar | None:
    return next((bar for bar in reversed(bars) if bar.date <= value), None)


def _candidate_story(
    *,
    state: DecisionState,
    strategy_name: str,
    target_weight_pct: float,
    first_discovered_on: dt.date,
) -> tuple[str, str]:
    if state == "ready":
        return (
            "Entry target is waiting for execution",
            f"{strategy_name} formed a {target_weight_pct:.1f}% paper target after the "
            f"{first_discovered_on.isoformat()} completed session. Risk and liquidity checks still "
            "control the next eligible fill.",
        )
    if state == "manage":
        return (
            "Paper position remains active",
            f"{strategy_name} continues to hold this name with a {target_weight_pct:.1f}% target. "
            "The return shown starts at first discovery, not at an assumed fill.",
        )
    if state == "exit":
        return (
            "Exit target is waiting for execution",
            f"{strategy_name} removed the target while the paper position is still open. The next "
            "eligible session remains subject to price availability, liquidity, and costs.",
        )
    if state == "blocked":
        return (
            "The desired action was blocked",
            f"{strategy_name} produced an instruction, but a portfolio or execution constraint "
            "prevented Atlas from representing it as a completed paper trade.",
        )
    return (
        "The paper position is closed",
        f"{strategy_name} no longer has an active target or position. The archived discovery and "
        "price outcome remain available for evaluation.",
    )


def _candidate_codes(
    snapshot: ResearchShadowSnapshot,
    snapshot_events: Iterable[ResearchDecisionEvent],
) -> set[str]:
    codes = set(snapshot.positions) | set(snapshot.target_weights)
    codes.update(event.code for event in snapshot_events if event.code)
    return {code.upper() for code in codes if code}


async def load_decision_board(
    session: AsyncSession,
    *,
    workspace: ResearchWorkspace,
    as_of: dt.date | None = None,
) -> DecisionBoardOut:
    """Load an immutable daily strategy view for one exact Atlas workspace."""

    portfolios = list(
        await session.scalars(
            select(ResearchShadowPortfolio)
            .where(
                ResearchShadowPortfolio.workspace_id == workspace.id,
                ResearchShadowPortfolio.organization_id == workspace.organization_id,
                ResearchShadowPortfolio.tenant_id == workspace.tenant_id,
                ResearchShadowPortfolio.market == workspace.market,
            )
            .order_by(ResearchShadowPortfolio.created_at)
        )
    )
    if not portfolios:
        return DecisionBoardOut(
            workspace_id=workspace.id,
            tenant_id=workspace.tenant_id,
            market=workspace.market,
            generated_at=dt.datetime.now(dt.UTC),
            selected_date=None,
            latest_date=None,
            available_dates=[],
            direction_capabilities=direction_capabilities(workspace.market),
            candidates=[],
            methodology=(
                "No shadow strategy book exists in this workspace. Atlas does not manufacture "
                "trade candidates from research-queue urgency."
            ),
        )

    portfolio_ids = [portfolio.id for portfolio in portfolios]
    available_dates = list(
        await session.scalars(
            select(ResearchShadowSnapshot.as_of_date)
            .join(
                ResearchShadowPortfolio,
                ResearchShadowPortfolio.id == ResearchShadowSnapshot.portfolio_id,
            )
            .where(
                ResearchShadowPortfolio.workspace_id == workspace.id,
                ResearchShadowPortfolio.organization_id == workspace.organization_id,
                ResearchShadowPortfolio.tenant_id == workspace.tenant_id,
                ResearchShadowPortfolio.market == workspace.market,
                ResearchShadowSnapshot.organization_id == workspace.organization_id,
                ResearchShadowSnapshot.tenant_id == workspace.tenant_id,
                ResearchShadowSnapshot.market == workspace.market,
            )
            .distinct()
            .order_by(ResearchShadowSnapshot.as_of_date.desc())
            .limit(260)
        )
    )
    latest_date = available_dates[0] if available_dates else None
    eligible_dates = [value for value in available_dates if as_of is None or value <= as_of]
    selected_date = eligible_dates[0] if eligible_dates else None
    if selected_date is None:
        return DecisionBoardOut(
            workspace_id=workspace.id,
            tenant_id=workspace.tenant_id,
            market=workspace.market,
            generated_at=dt.datetime.now(dt.UTC),
            selected_date=None,
            latest_date=latest_date,
            available_dates=available_dates,
            direction_capabilities=direction_capabilities(workspace.market),
            candidates=[],
            methodology="No strategy snapshot exists on or before the requested date.",
        )

    selected_snapshots = []
    for portfolio in portfolios:
        snapshot = await session.scalar(
            select(ResearchShadowSnapshot)
            .where(
                ResearchShadowSnapshot.portfolio_id == portfolio.id,
                ResearchShadowSnapshot.organization_id == workspace.organization_id,
                ResearchShadowSnapshot.tenant_id == workspace.tenant_id,
                ResearchShadowSnapshot.market == workspace.market,
                ResearchShadowSnapshot.as_of_date <= selected_date,
            )
            .order_by(ResearchShadowSnapshot.as_of_date.desc())
            .limit(1)
        )
        if snapshot is not None:
            selected_snapshots.append(snapshot)
    snapshot_ids = [snapshot.id for snapshot in selected_snapshots]

    events = list(
        await session.scalars(
            select(ResearchDecisionEvent)
            .where(
                ResearchDecisionEvent.workspace_id == workspace.id,
                ResearchDecisionEvent.organization_id == workspace.organization_id,
                ResearchDecisionEvent.tenant_id == workspace.tenant_id,
                ResearchDecisionEvent.market == workspace.market,
                ResearchDecisionEvent.portfolio_id.in_(portfolio_ids),
                ResearchDecisionEvent.code.is_not(None),
                ResearchDecisionEvent.effective_date <= selected_date,
            )
            .order_by(ResearchDecisionEvent.sequence)
        )
    )
    events_by_pair: dict[tuple[uuid.UUID, str], list[ResearchDecisionEvent]] = defaultdict(list)
    events_by_snapshot: dict[uuid.UUID, list[ResearchDecisionEvent]] = defaultdict(list)
    events_by_snapshot_pair: dict[tuple[uuid.UUID, uuid.UUID, str], list[ResearchDecisionEvent]] = (
        defaultdict(list)
    )
    for event in events:
        if event.snapshot_id in snapshot_ids:
            events_by_snapshot[event.snapshot_id].append(event)
        if not event.code:
            continue
        code = event.code.upper()
        events_by_pair[(event.portfolio_id, code)].append(event)
        if event.snapshot_id in snapshot_ids:
            events_by_snapshot_pair[(event.portfolio_id, event.snapshot_id, code)].append(event)

    candidate_pairs: list[tuple[ResearchShadowPortfolio, ResearchShadowSnapshot, str]] = []
    portfolio_by_id = {portfolio.id: portfolio for portfolio in portfolios}
    for snapshot in selected_snapshots:
        portfolio = portfolio_by_id[snapshot.portfolio_id]
        snapshot_events = events_by_snapshot[snapshot.id]
        current_codes = _candidate_codes(snapshot, snapshot_events)
        for code in sorted(current_codes):
            candidate_pairs.append((portfolio, snapshot, code))
        # Recently closed positions stay visible for accountability: a code whose last strategy
        # event fell inside the trailing window but which no longer carries a target, position,
        # or same-snapshot event is shown in its terminal "closed" state instead of vanishing
        # the day after it exited.
        recency_floor = selected_date - dt.timedelta(days=30)
        for (portfolio_id, code), pair_events in events_by_pair.items():
            if portfolio_id != portfolio.id or code in current_codes:
                continue
            if pair_events and pair_events[-1].effective_date >= recency_floor:
                candidate_pairs.append((portfolio, snapshot, code))

    codes = sorted({code for _, _, code in candidate_pairs})
    symbols = {
        symbol.code: symbol
        for symbol in list(
            await session.scalars(
                select(Symbol).where(Symbol.market == workspace.market, Symbol.code.in_(codes))
            )
        )
    }
    # Capitalization basis: prefer the recorded classification on or before the archived
    # session (cap_tier_observations, collection began 2026-07-24); fall back to the current
    # TickerAnalytics row where no history was ever recorded — and the methodology says which
    # basis applies. A tier the platform never recorded is never invented.
    analytics_rows = list(
        await session.scalars(
            select(TickerAnalytics).where(
                TickerAnalytics.market == workspace.market,
                TickerAnalytics.code.in_(codes),
            )
        )
    )
    analytics_by_code = {row.code: row for row in analytics_rows}
    recorded_tier_rows = list(
        await session.scalars(
            select(CapTierObservation)
            .where(
                CapTierObservation.market == workspace.market,
                CapTierObservation.code.in_(codes),
                CapTierObservation.as_of_date <= selected_date,
            )
            .distinct(CapTierObservation.code)
            .order_by(CapTierObservation.code, CapTierObservation.as_of_date.desc())
        )
    )
    recorded_tier_by_code = {row.code: row.cap_tier for row in recorded_tier_rows if row.cap_tier}

    def candidate_cap_tier(code: str) -> str:
        recorded = recorded_tier_by_code.get(code)
        if recorded:
            return recorded
        current = analytics_by_code.get(code)
        return current.cap_tier if current is not None and current.cap_tier else "unclassified"

    first_dates: dict[tuple[uuid.UUID, str], dt.date] = {}
    for portfolio, _, code in candidate_pairs:
        pair_events = events_by_pair[(portfolio.id, code)]
        signal = next((event for event in pair_events if event.event_type == "signal"), None)
        first_dates[(portfolio.id, code)] = (
            signal.effective_date if signal is not None else portfolio.inception_date
        )

    earliest_discovery = min(first_dates.values(), default=selected_date)
    bars = list(
        await session.scalars(
            select(DailyBar)
            .where(
                DailyBar.market == workspace.market,
                DailyBar.code.in_(codes),
                DailyBar.date >= earliest_discovery,
                DailyBar.date <= selected_date,
            )
            .order_by(DailyBar.code, DailyBar.date)
        )
    )
    bars_by_code: dict[str, list[DailyBar]] = defaultdict(list)
    for bar in bars:
        bars_by_code[bar.code].append(bar)

    candidates: list[DecisionCandidateOut] = []
    for portfolio, snapshot, code in candidate_pairs:
        pair_events = events_by_pair[(portfolio.id, code)]
        snapshot_events = events_by_snapshot_pair[(portfolio.id, snapshot.id, code)]
        target_weight = float(snapshot.target_weights.get(code, 0) or 0)
        position = snapshot.positions.get(code)
        state = derive_decision_state(
            target_weight=target_weight,
            has_position=position is not None,
            snapshot_events=snapshot_events,
        )
        discovery_date = first_dates[(portfolio.id, code)]
        code_bars = bars_by_code.get(code, [])
        reference_bar = _latest_bar_on_or_before(code_bars, discovery_date)
        as_of_bar = _latest_bar_on_or_before(code_bars, snapshot.as_of_date)
        discovery_price = adjusted_close(reference_bar) if reference_bar is not None else None
        as_of_price = adjusted_close(as_of_bar) if as_of_bar is not None else None
        path_prices = [
            adjusted_close(bar)
            for bar in code_bars
            if reference_bar is not None and reference_bar.date <= bar.date <= snapshot.as_of_date
        ]
        return_pct, maximum_favorable, maximum_adverse = discovery_performance(
            path_prices,
            reference_price=discovery_price,
        )
        fills = [event for event in pair_events if event.event_type == "fill"]
        latest_fill = fills[-1] if fills else None
        fill_side = (
            str(latest_fill.payload.get("side", "")).lower() if latest_fill is not None else ""
        )
        latest_fill_side: Literal["buy", "sell"] | None = (
            fill_side if fill_side in {"buy", "sell"} else None
        )
        latest_fill_price_value = (
            latest_fill.payload.get("fill_price") if latest_fill is not None else None
        )
        latest_fill_price = (
            float(latest_fill_price_value)
            if isinstance(latest_fill_price_value, (int, float))
            else None
        )
        target_weight_pct = target_weight * 100
        shares = int(position.get("shares", 0)) if isinstance(position, dict) else 0
        position_weight_pct = (
            shares * as_of_price / float(snapshot.nav) * 100
            if shares > 0 and as_of_price is not None and float(snapshot.nav) > 0
            else 0
        )
        average_cost_value = position.get("average_cost") if isinstance(position, dict) else None
        average_cost = (
            float(average_cost_value)
            if isinstance(average_cost_value, (int, float)) and average_cost_value > 0
            else None
        )
        stop_loss = portfolio_stop_loss(portfolio, workspace.market)
        risk_reference, invalidation_price, planning_objective = price_plan(
            state=state,
            as_of_price=as_of_price,
            average_cost=average_cost,
            stop_loss=stop_loss,
        )
        strategy = STRATEGIES[portfolio.strategy_key]
        strategy_name = strategy.name
        horizon, expected_holding = strategy.horizon, strategy.expected_holding
        headline, story = _candidate_story(
            state=state,
            strategy_name=strategy_name,
            target_weight_pct=target_weight_pct,
            first_discovered_on=discovery_date,
        )
        risk_notes = []
        evidence_mode: Literal["forward", "historical_replay"] = (
            "forward"
            if snapshot.as_of_date >= _forward_evidence_started_on(portfolio)
            else "historical_replay"
        )
        if evidence_mode == "historical_replay":
            risk_notes.append(
                "This archived state was replayed from completed historical sessions using the "
                "engine's execution rules, but universe membership, liquidity ranking and "
                "capitalization filters use current classifications, not point-in-time records. "
                "It is excluded from forward paper-promotion evidence."
            )
        if not adjustment_complete(
            [
                bar
                for bar in code_bars
                if reference_bar is not None and bar.date >= reference_bar.date
            ]
        ):
            risk_notes.append(
                "Prices are raw exchange closes without corporate-action adjustment. A split, "
                "bonus or rights issue in this window would distort the measured return, MFE "
                "and MAE."
            )
        if snapshot.as_of_date < selected_date:
            risk_notes.append(
                f"This strategy book was last evaluated on {snapshot.as_of_date.isoformat()}, "
                f"before the selected {selected_date.isoformat()} archive date."
            )
        for event in snapshot_events:
            if event.event_type not in {"risk", "rejection"}:
                continue
            detail = event.payload.get("detail")
            rule = str(event.payload.get("rule", event.event_type)).replace("_", " ")
            risk_notes.append(str(detail) if detail else rule)
        candidates.append(
            DecisionCandidateOut(
                id=f"{portfolio.id}:{code}",
                portfolio_id=portfolio.id,
                portfolio_name=portfolio.name,
                strategy_key=portfolio.strategy_key,
                strategy_name=strategy_name,
                direction="long",
                horizon=horizon,
                expected_holding=expected_holding,
                code=code,
                company=symbols[code].name_en if code in symbols else code,
                cap_tier=candidate_cap_tier(code),
                state=state,
                evidence_mode=evidence_mode,
                as_of_date=snapshot.as_of_date,
                first_discovered_on=discovery_date,
                is_new=discovery_date == snapshot.as_of_date,
                discovery_price=discovery_price,
                as_of_price=as_of_price,
                return_since_discovery_pct=return_pct,
                max_favorable_pct=maximum_favorable,
                max_adverse_pct=maximum_adverse,
                sessions_since_discovery=len(path_prices),
                target_weight_pct=round(target_weight_pct, 3),
                position_weight_pct=round(position_weight_pct, 3),
                latest_fill_side=latest_fill_side,
                latest_fill_price=latest_fill_price,
                latest_fill_date=latest_fill.effective_date if latest_fill is not None else None,
                risk_reference_price=risk_reference,
                invalidation_price=invalidation_price,
                planning_objective_price=planning_objective,
                planning_reward_risk=2.0 if planning_objective is not None else None,
                exit_policy=(
                    f"Position stop: {stop_loss:.0%} below average cost after fill; strategy "
                    "target removal, portfolio constraints and the drawdown ladder can exit sooner."
                ),
                headline=headline,
                story=story,
                risk_notes=risk_notes,
            )
        )

    candidates.sort(
        key=lambda candidate: (
            _STATE_ORDER[candidate.state],
            not candidate.is_new,
            -candidate.first_discovered_on.toordinal(),
            candidate.code,
        )
    )
    return DecisionBoardOut(
        workspace_id=workspace.id,
        tenant_id=workspace.tenant_id,
        market=workspace.market,
        generated_at=dt.datetime.now(dt.UTC),
        selected_date=selected_date,
        latest_date=latest_date,
        available_dates=available_dates,
        direction_capabilities=direction_capabilities(workspace.market),
        candidates=candidates,
        methodology=(
            "Archived states come from immutable shadow snapshots and decision events. "
            + (
                "Performance uses split/distribution-adjusted completed closes from first "
                "discovery through the selected date. "
                if adjustment_complete(bars)
                else "Performance uses completed closes from first discovery through the "
                "selected date; where no audited adjustment factor exists the close is the raw "
                "exchange print, and affected candidates carry an explicit corporate-action "
                "warning. "
            )
            + "Capitalization uses the classification recorded on or before the archived "
            "session where a recorded history exists (collection began 2026-07-24); earlier "
            "archive dates fall back to the latest known classification. A target is not a "
            "completed fill or a recommendation; a 2R objective is a risk-planning reference, "
            "not a price forecast."
        ),
    )


async def load_decision_candidate_path(
    session: AsyncSession,
    *,
    workspace: ResearchWorkspace,
    portfolio_id: uuid.UUID,
    code: str,
    as_of: dt.date | None = None,
) -> DecisionCandidatePathOut:
    """Load chart-ready price and event history for one archived candidate."""

    normalized_code = code.strip().upper()
    board = await load_decision_board(session, workspace=workspace, as_of=as_of)
    candidate = next(
        (
            item
            for item in board.candidates
            if item.portfolio_id == portfolio_id and item.code == normalized_code
        ),
        None,
    )
    if candidate is None:
        raise LookupError("decision candidate not found in this workspace snapshot")

    context_start = candidate.first_discovered_on - dt.timedelta(days=180)
    bars = list(
        await session.scalars(
            select(DailyBar)
            .where(
                DailyBar.market == workspace.market,
                DailyBar.code == normalized_code,
                DailyBar.date >= context_start,
                DailyBar.date <= candidate.as_of_date,
            )
            .order_by(DailyBar.date)
        )
    )
    reference_bar = _latest_bar_on_or_before(bars, candidate.first_discovered_on)
    reference_price = adjusted_close(reference_bar) if reference_bar is not None else None
    points = [
        DecisionPricePointOut(
            date=bar.date,
            close=adjusted_close(bar),
            volume=bar.volume,
            return_since_discovery_pct=(
                round((adjusted_close(bar) / reference_price - 1) * 100, 3)
                if reference_price is not None and bar.date >= candidate.first_discovered_on
                else None
            ),
        )
        for bar in bars
    ]
    events = list(
        await session.scalars(
            select(ResearchDecisionEvent)
            .where(
                ResearchDecisionEvent.workspace_id == workspace.id,
                ResearchDecisionEvent.organization_id == workspace.organization_id,
                ResearchDecisionEvent.tenant_id == workspace.tenant_id,
                ResearchDecisionEvent.market == workspace.market,
                ResearchDecisionEvent.portfolio_id == portfolio_id,
                ResearchDecisionEvent.code == normalized_code,
                ResearchDecisionEvent.effective_date <= candidate.as_of_date,
            )
            .order_by(ResearchDecisionEvent.sequence)
        )
    )
    return DecisionCandidatePathOut(
        workspace_id=workspace.id,
        tenant_id=workspace.tenant_id,
        market=workspace.market,
        candidate=candidate,
        points=points,
        events=[_event_out(event) for event in events],
        price_basis=(
            (
                "Adjusted completed-session close. The archived strategy state is immutable; "
                "later corporate-action adjustments may restate the displayed historical price "
                "scale."
            )
            if adjustment_complete(bars)
            else (
                "Raw completed-session close — no audited corporate-action adjustment exists "
                "for this history. A split, bonus or rights issue inside this window appears as "
                "a price move, not a neutral adjustment."
            )
        ),
    )
