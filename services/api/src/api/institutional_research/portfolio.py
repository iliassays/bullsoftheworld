"""Atlas shadow-book persistence and forward calibration."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.institutional_research.investment import (
    get_active_mandate,
    mandate_snapshot,
    mark_trial_shadow,
    record_snapshot_decision_events,
    risk_policy_from_snapshot,
)
from api.institutional_research.schemas import (
    BacktestRequest,
    CalibrationObservationOut,
    CalibrationOut,
    CreateShadowPortfolioRequest,
    ResearchShadowPortfolioOut,
    ResearchShadowSnapshotOut,
)
from api.institutional_research.workflow import _backtest_universe, load_research_run
from bulls.analytics.research_strategy import (
    ENGINE_VERSION,
    ShadowAccountingEvent,
    ShadowState,
    advance_shadow_portfolio,
    evaluate_shadow_promotion,
    methodology_boundary_accounting_events,
    opening_accounting_events,
    replay_accounting_events,
)
from bulls.core.models import (
    DailyBar,
    ResearchAccountingEvent,
    ResearchOutcomeObservation,
    ResearchShadowPortfolio,
    ResearchShadowSnapshot,
    ResearchStrategyTrial,
    ResearchWorkspace,
)


def _payload_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _accounting_event_hash(event: ShadowAccountingEvent) -> str:
    """Fingerprint the complete economic identity, not only its mutable payload field."""

    return _payload_hash(
        {
            "event_key": event.event_key,
            "session_number": event.session_number,
            "effective_date": event.effective_date,
            "event_type": event.event_type,
            "code": event.code,
            "engine_version": ENGINE_VERSION,
            "payload": event.payload,
        }
    )


def _state_from_snapshot(snapshot: ResearchShadowSnapshot) -> ShadowState:
    return ShadowState(
        cash=float(snapshot.cash),
        positions=snapshot.positions,
        pending_settlements=snapshot.pending_settlements,
        peak_nav=float(snapshot.peak_nav),
        benchmark_nav=float(snapshot.benchmark_nav),
        cumulative_fees=float(snapshot.cumulative_fees),
        cumulative_turnover=float(snapshot.cumulative_turnover),
    )


async def _record_accounting_events(
    session: AsyncSession,
    *,
    portfolio: ResearchShadowPortfolio,
    events: list[ShadowAccountingEvent],
) -> None:
    """Persist idempotent accounting authority before accepting its snapshot projection."""

    existing_rows = (
        await session.execute(
            select(
                ResearchAccountingEvent.event_key,
                ResearchAccountingEvent.payload_hash,
            ).where(
                ResearchAccountingEvent.portfolio_id == portfolio.id,
                ResearchAccountingEvent.organization_id == portfolio.organization_id,
                ResearchAccountingEvent.tenant_id == portfolio.tenant_id,
                ResearchAccountingEvent.market == portfolio.market,
            )
        )
    ).all()
    existing = {str(key): str(payload_hash) for key, payload_hash in existing_rows}
    maximum_sequence = await session.scalar(
        select(func.max(ResearchAccountingEvent.sequence)).where(
            ResearchAccountingEvent.portfolio_id == portfolio.id,
            ResearchAccountingEvent.organization_id == portfolio.organization_id,
            ResearchAccountingEvent.tenant_id == portfolio.tenant_id,
            ResearchAccountingEvent.market == portfolio.market,
        )
    )
    sequence = int(maximum_sequence) + 1 if maximum_sequence is not None else 0
    inserted = 0
    for event in events:
        payload_hash = _accounting_event_hash(event)
        if event.event_key in existing:
            if existing[event.event_key] != payload_hash:
                raise RuntimeError(
                    f"Accounting event {event.event_key} was retried with a different economic identity"
                )
            continue
        session.add(
            ResearchAccountingEvent(
                id=uuid.uuid4(),
                organization_id=portfolio.organization_id,
                workspace_id=portfolio.workspace_id,
                tenant_id=portfolio.tenant_id,
                market=portfolio.market,
                portfolio_id=portfolio.id,
                sequence=sequence + inserted,
                session_number=event.session_number,
                event_key=event.event_key,
                event_type=event.event_type,
                code=event.code,
                effective_date=event.effective_date,
                engine_version=ENGINE_VERSION,
                payload=event.payload,
                payload_hash=payload_hash,
            )
        )
        inserted += 1
    await session.flush()


async def _ensure_accounting_boundary(
    session: AsyncSession,
    *,
    portfolio: ResearchShadowPortfolio,
    latest: ResearchShadowSnapshot,
) -> None:
    existing = await session.scalar(
        select(ResearchAccountingEvent.id)
        .where(
            ResearchAccountingEvent.portfolio_id == portfolio.id,
            ResearchAccountingEvent.organization_id == portfolio.organization_id,
            ResearchAccountingEvent.tenant_id == portfolio.tenant_id,
            ResearchAccountingEvent.market == portfolio.market,
        )
        .limit(1)
    )
    if existing is not None:
        return
    await _record_accounting_events(
        session,
        portfolio=portfolio,
        events=methodology_boundary_accounting_events(
            state=_state_from_snapshot(latest),
            session_number=latest.session_number,
            effective_date=latest.as_of_date,
            source_snapshot_id=str(latest.id),
        ),
    )


def _snapshot_out(snapshot: ResearchShadowSnapshot) -> ResearchShadowSnapshotOut:
    return ResearchShadowSnapshotOut(
        id=snapshot.id,
        as_of_date=snapshot.as_of_date,
        session_number=snapshot.session_number,
        nav=float(snapshot.nav),
        cash=float(snapshot.cash),
        benchmark_nav=float(snapshot.benchmark_nav),
        peak_nav=float(snapshot.peak_nav),
        gross_exposure_pct=float(snapshot.gross_exposure_pct),
        drawdown_pct=float(snapshot.drawdown_pct),
        cumulative_fees=float(snapshot.cumulative_fees),
        cumulative_turnover=float(snapshot.cumulative_turnover),
        positions=snapshot.positions,
        pending_settlements=snapshot.pending_settlements,
        target_weights=snapshot.target_weights,
        trades=snapshot.trades,
        risk_interventions=snapshot.risk_interventions,
    )


async def _snapshots(
    session: AsyncSession, *, portfolio: ResearchShadowPortfolio, limit: int = 260
) -> list[ResearchShadowSnapshot]:
    rows = list(
        await session.scalars(
            select(ResearchShadowSnapshot)
            .where(
                ResearchShadowSnapshot.portfolio_id == portfolio.id,
                ResearchShadowSnapshot.organization_id == portfolio.organization_id,
                ResearchShadowSnapshot.tenant_id == portfolio.tenant_id,
                ResearchShadowSnapshot.market == portfolio.market,
            )
            .order_by(ResearchShadowSnapshot.as_of_date.desc())
            .limit(limit)
        )
    )
    return list(reversed(rows))


async def _portfolio_out(
    session: AsyncSession, portfolio: ResearchShadowPortfolio
) -> ResearchShadowPortfolioOut:
    snapshots = await _snapshots(session, portfolio=portfolio)
    return ResearchShadowPortfolioOut(
        id=portfolio.id,
        workspace_id=portfolio.workspace_id,
        tenant_id=portfolio.tenant_id,
        market=portfolio.market,
        source_run_id=portfolio.source_run_id,
        name=portfolio.name,
        strategy_key=portfolio.strategy_key,
        status=portfolio.status,
        initial_capital=float(portfolio.initial_capital),
        inception_date=portfolio.inception_date,
        last_evaluated_on=portfolio.last_evaluated_on,
        configuration=portfolio.configuration,
        snapshots=[_snapshot_out(snapshot) for snapshot in snapshots],
    )


async def create_shadow_portfolio(
    session: AsyncSession,
    *,
    workspace: ResearchWorkspace,
    user_id: int,
    request: CreateShadowPortfolioRequest,
) -> ResearchShadowPortfolioOut:
    await session.execute(
        select(ResearchWorkspace.id)
        .where(
            ResearchWorkspace.id == workspace.id,
            ResearchWorkspace.organization_id == workspace.organization_id,
            ResearchWorkspace.tenant_id == workspace.tenant_id,
            ResearchWorkspace.market == workspace.market,
        )
        .with_for_update()
    )
    existing_source = await session.scalar(
        select(ResearchShadowPortfolio.id).where(
            ResearchShadowPortfolio.workspace_id == workspace.id,
            ResearchShadowPortfolio.organization_id == workspace.organization_id,
            ResearchShadowPortfolio.tenant_id == workspace.tenant_id,
            ResearchShadowPortfolio.market == workspace.market,
            ResearchShadowPortfolio.source_run_id == request.source_run_id,
            ResearchShadowPortfolio.status != "archived",
        )
    )
    if existing_source is not None:
        raise ValueError("This registered trial already has a concurrent shadow book")
    concurrent_books = int(
        await session.scalar(
            select(func.count(ResearchShadowPortfolio.id)).where(
                ResearchShadowPortfolio.workspace_id == workspace.id,
                ResearchShadowPortfolio.organization_id == workspace.organization_id,
                ResearchShadowPortfolio.tenant_id == workspace.tenant_id,
                ResearchShadowPortfolio.market == workspace.market,
                ResearchShadowPortfolio.status.in_(("active", "paused")),
            )
        )
        or 0
    )
    if concurrent_books >= 3:
        raise ValueError("The workspace already has the maximum of three concurrent shadow books")
    run = await load_research_run(session, workspace=workspace, run_id=request.source_run_id)
    if run.run_kind != "hypothesis" or run.status != "succeeded":
        raise ValueError("A shadow portfolio requires a completed hypothesis backtest")
    backtest_step = next((step for step in run.steps if step.kind == "portfolio_backtest"), None)
    if backtest_step is None:
        raise ValueError("The source run does not contain a portfolio backtest")
    result = backtest_step.output
    end_date = result.get("end_date")
    if not end_date:
        raise ValueError("The source backtest has no completed market session")
    strategy = result["strategy"]
    if strategy["market"] != workspace.market:
        raise ValueError("The source strategy belongs to another market")
    initial_capital = Decimal(str(result["initial_capital"]))
    universe_step = next((step for step in run.steps if step.kind == "observable_universe"), None)
    observable_codes = (
        [str(code) for code in universe_step.output.get("codes", [])]
        if universe_step is not None
        else []
    )
    backtest_request = {
        key: value for key, value in run.parameters.items() if key not in {"result_summary"}
    }
    # A forward test must retain the universe observable at inception. Re-selecting today's most
    # liquid names on every reconciliation would introduce survivorship and universe drift.
    backtest_request["codes"] = observable_codes
    backtest_request["universe_limit"] = max(5, min(500, len(observable_codes) or 5))
    mandate = await get_active_mandate(session, workspace=workspace)
    if mandate is None:
        raise ValueError("An active investment mandate is required before starting a shadow book")
    pinned_mandate = mandate_snapshot(mandate)
    portfolio = ResearchShadowPortfolio(
        id=uuid.uuid4(),
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        tenant_id=workspace.tenant_id,
        market=workspace.market,
        source_run_id=run.id,
        created_by_user_id=user_id,
        name=request.name,
        strategy_key=strategy["key"],
        status="active",
        initial_capital=initial_capital,
        inception_date=dt.date.fromisoformat(end_date),
        last_evaluated_on=dt.date.fromisoformat(end_date),
        configuration={
            "backtest_request": backtest_request,
            "observable_universe": observable_codes,
            "source_validation_status": result["validation_status"],
            "source_failed_gates": result["failed_gates"],
            "engine_version": result["engine_version"],
            "accounting_methodology_version": "event-first-v1",
            "mandate": pinned_mandate,
            "mandate_binding": "pinned_at_inception",
        },
    )
    session.add(portfolio)
    await session.flush()
    opening_events = opening_accounting_events(
        initial_capital=float(initial_capital),
        effective_date=portfolio.inception_date,
    )
    opening_state = replay_accounting_events(None, opening_events)
    await _record_accounting_events(
        session,
        portfolio=portfolio,
        events=opening_events,
    )
    initial_snapshot = ResearchShadowSnapshot(
        id=uuid.uuid4(),
        portfolio_id=portfolio.id,
        organization_id=workspace.organization_id,
        tenant_id=workspace.tenant_id,
        market=workspace.market,
        as_of_date=portfolio.inception_date,
        session_number=0,
        nav=Decimal(str(opening_state.cash)),
        cash=Decimal(str(opening_state.cash)),
        benchmark_nav=Decimal(str(opening_state.benchmark_nav)),
        peak_nav=Decimal(str(opening_state.peak_nav)),
        gross_exposure_pct=Decimal("0"),
        drawdown_pct=Decimal("0"),
        cumulative_fees=Decimal(str(opening_state.cumulative_fees)),
        cumulative_turnover=Decimal(str(opening_state.cumulative_turnover)),
        positions={
            code: position.model_dump(mode="json")
            for code, position in opening_state.positions.items()
        },
        pending_settlements=[
            settlement.model_dump(mode="json") for settlement in opening_state.pending_settlements
        ],
        target_weights=result["latest_target_weights"],
        trades=[],
        risk_interventions=[],
    )
    session.add(initial_snapshot)
    await session.flush()
    await record_snapshot_decision_events(
        session,
        portfolio=portfolio,
        snapshot=initial_snapshot,
        previous=None,
    )
    await mark_trial_shadow(session, source_run_id=run.id, workspace=workspace)
    await _evaluate_portfolio_promotion(session, portfolio=portfolio)
    return await _portfolio_out(session, portfolio)


async def _evaluate_portfolio_promotion(
    session: AsyncSession,
    *,
    portfolio: ResearchShadowPortfolio,
) -> None:
    snapshots = await _snapshots(session, portfolio=portfolio, limit=5000)
    if not snapshots:
        return
    first = snapshots[0]
    latest = snapshots[-1]
    decision = evaluate_shadow_promotion(
        source_validation_status=str(
            portfolio.configuration.get("source_validation_status", "diagnostic")
        ),
        initial_nav=float(first.nav),
        latest_nav=float(latest.nav),
        initial_benchmark_nav=float(first.benchmark_nav),
        latest_benchmark_nav=float(latest.benchmark_nav),
        sessions=latest.session_number,
        maximum_drawdown_pct=max(float(snapshot.drawdown_pct) for snapshot in snapshots),
        executions=sum(len(snapshot.trades) for snapshot in snapshots),
    )
    portfolio.configuration = {
        **portfolio.configuration,
        "promotion": {
            **decision.model_dump(mode="json"),
            "policy_version": "atlas-promotion-policy-v1",
            "policy_role": "early_evidence_review_floor",
            "evaluated_on": latest.as_of_date.isoformat(),
            "capital_action": "none",
        },
    }
    trial = await session.scalar(
        select(ResearchStrategyTrial).where(
            ResearchStrategyTrial.source_run_id == portfolio.source_run_id,
            ResearchStrategyTrial.workspace_id == portfolio.workspace_id,
            ResearchStrategyTrial.organization_id == portfolio.organization_id,
            ResearchStrategyTrial.tenant_id == portfolio.tenant_id,
            ResearchStrategyTrial.market == portfolio.market,
        )
    )
    if trial is not None:
        trial.status = (
            "eligible"
            if decision.status == "eligible"
            else "rejected"
            if decision.status == "rejected"
            else "shadow"
        )
    await session.flush()


async def _refresh_shadow_portfolio(
    session: AsyncSession,
    *,
    portfolio: ResearchShadowPortfolio,
) -> None:
    latest = (
        await session.scalars(
            select(ResearchShadowSnapshot)
            .where(
                ResearchShadowSnapshot.portfolio_id == portfolio.id,
                ResearchShadowSnapshot.organization_id == portfolio.organization_id,
                ResearchShadowSnapshot.tenant_id == portfolio.tenant_id,
                ResearchShadowSnapshot.market == portfolio.market,
            )
            .order_by(ResearchShadowSnapshot.as_of_date.desc())
            .limit(1)
        )
    ).one()
    latest_market_date = await session.scalar(
        select(DailyBar.date)
        .where(DailyBar.market == portfolio.market)
        .order_by(DailyBar.date.desc())
        .limit(1)
    )
    if latest_market_date is None or latest_market_date <= latest.as_of_date:
        return
    pinned_mandate = portfolio.configuration.get("mandate")
    if not isinstance(pinned_mandate, dict):
        portfolio.status = "paused"
        portfolio.configuration = {
            **portfolio.configuration,
            "refresh_error": (
                "Shadow advancement stopped because this legacy book has no pinned investment "
                "mandate. Recreate it from its registered trial."
            ),
        }
        await session.flush()
        return
    risk_policy = risk_policy_from_snapshot(pinned_mandate, portfolio.market)
    request_data = dict(portfolio.configuration.get("backtest_request", {}))
    request_data.update(
        {
            "idempotency_key": f"shadow-{portfolio.id}",
            "strategy_key": portfolio.strategy_key,
            "end_date": latest_market_date,
        }
    )
    request = BacktestRequest.model_validate(request_data)
    securities = await _backtest_universe(session, market=portfolio.market, request=request)
    pending_dates = sorted(
        {
            bar.date
            for security in securities
            for bar in security.bars
            if latest.as_of_date < bar.date <= latest_market_date
        }
    )
    await _ensure_accounting_boundary(
        session,
        portfolio=portfolio,
        latest=latest,
    )
    for current_date in pending_dates:
        current_securities = []
        for security in securities:
            history = [bar for bar in security.bars if bar.date <= current_date]
            if history and history[-1].date == current_date:
                current_securities.append(security.model_copy(update={"bars": history}))
        held_codes = set(latest.positions)
        if not held_codes <= {security.code for security in current_securities}:
            missing = sorted(held_codes - {security.code for security in current_securities})
            portfolio.status = "paused"
            portfolio.configuration = {
                **portfolio.configuration,
                "refresh_error": (
                    "Shadow advancement stopped because held securities lacked a completed "
                    f"bar for {current_date.isoformat()}: {', '.join(missing)}"
                ),
            }
            break
        previous_snapshot = latest
        previous = _state_from_snapshot(latest)
        advanced = advance_shadow_portfolio(
            market=portfolio.market,
            strategy_key=portfolio.strategy_key,
            securities=current_securities,
            previous=previous,
            target_weights={key: float(value) for key, value in latest.target_weights.items()},
            session_number=latest.session_number + 1,
            risk_policy=risk_policy,
        )
        replayed_state = replay_accounting_events(previous, advanced.accounting_events)
        if _payload_hash(replayed_state.model_dump(mode="json")) != _payload_hash(
            advanced.state.model_dump(mode="json")
        ):
            raise RuntimeError(
                f"Accounting replay did not reconcile shadow session {latest.session_number + 1}"
            )
        await _record_accounting_events(
            session,
            portfolio=portfolio,
            events=advanced.accounting_events,
        )
        latest = ResearchShadowSnapshot(
            id=uuid.uuid4(),
            portfolio_id=portfolio.id,
            organization_id=portfolio.organization_id,
            tenant_id=portfolio.tenant_id,
            market=portfolio.market,
            as_of_date=advanced.date,
            session_number=latest.session_number + 1,
            nav=Decimal(str(advanced.nav)),
            cash=Decimal(str(replayed_state.cash)),
            benchmark_nav=Decimal(str(replayed_state.benchmark_nav)),
            peak_nav=Decimal(str(replayed_state.peak_nav)),
            gross_exposure_pct=Decimal(str(advanced.gross_exposure_pct)),
            drawdown_pct=Decimal(str(advanced.drawdown_pct)),
            cumulative_fees=Decimal(str(replayed_state.cumulative_fees)),
            cumulative_turnover=Decimal(str(replayed_state.cumulative_turnover)),
            positions={
                code: position.model_dump(mode="json")
                for code, position in replayed_state.positions.items()
            },
            pending_settlements=[
                settlement.model_dump(mode="json")
                for settlement in replayed_state.pending_settlements
            ],
            target_weights=advanced.next_target_weights,
            trades=[trade.model_dump(mode="json") for trade in advanced.trades],
            risk_interventions=[
                intervention.model_dump(mode="json") for intervention in advanced.risk_interventions
            ],
        )
        session.add(latest)
        portfolio.last_evaluated_on = advanced.date
        await session.flush()
        await record_snapshot_decision_events(
            session,
            portfolio=portfolio,
            snapshot=latest,
            previous=previous_snapshot,
        )
    await _evaluate_portfolio_promotion(session, portfolio=portfolio)


async def list_shadow_portfolios(
    session: AsyncSession, *, workspace: ResearchWorkspace
) -> list[ResearchShadowPortfolioOut]:
    portfolios = list(
        await session.scalars(
            select(ResearchShadowPortfolio)
            .where(
                ResearchShadowPortfolio.workspace_id == workspace.id,
                ResearchShadowPortfolio.organization_id == workspace.organization_id,
                ResearchShadowPortfolio.tenant_id == workspace.tenant_id,
                ResearchShadowPortfolio.market == workspace.market,
            )
            .order_by(ResearchShadowPortfolio.created_at.desc())
        )
    )
    return [await _portfolio_out(session, portfolio) for portfolio in portfolios]


async def reconcile_shadow_portfolios(
    session: AsyncSession, *, workspace: ResearchWorkspace
) -> list[ResearchShadowPortfolioOut]:
    """Idempotently catch active books up to the latest completed EOD session."""

    portfolios = list(
        await session.scalars(
            select(ResearchShadowPortfolio)
            .where(
                ResearchShadowPortfolio.workspace_id == workspace.id,
                ResearchShadowPortfolio.organization_id == workspace.organization_id,
                ResearchShadowPortfolio.tenant_id == workspace.tenant_id,
                ResearchShadowPortfolio.market == workspace.market,
                ResearchShadowPortfolio.status == "active",
            )
            .with_for_update()
        )
    )
    for portfolio in portfolios:
        await _refresh_shadow_portfolio(session, portfolio=portfolio)
    return await list_shadow_portfolios(session, workspace=workspace)


async def refresh_outcome_observations(
    session: AsyncSession, *, workspace: ResearchWorkspace
) -> CalibrationOut:
    observations = list(
        await session.scalars(
            select(ResearchOutcomeObservation)
            .where(
                ResearchOutcomeObservation.workspace_id == workspace.id,
                ResearchOutcomeObservation.organization_id == workspace.organization_id,
                ResearchOutcomeObservation.tenant_id == workspace.tenant_id,
                ResearchOutcomeObservation.market == workspace.market,
            )
            .order_by(ResearchOutcomeObservation.reference_date.desc())
        )
    )
    for observation in observations:
        if observation.status != "pending":
            continue
        bars = list(
            await session.scalars(
                select(DailyBar)
                .where(
                    DailyBar.market == observation.market,
                    DailyBar.code == observation.code,
                    DailyBar.date > observation.reference_date,
                )
                .order_by(DailyBar.date)
                .limit(observation.horizon_sessions)
            )
        )
        if len(bars) < observation.horizon_sessions:
            continue
        prices = [
            float(bar.adjusted_close if bar.adjusted_close is not None else bar.close)
            for bar in bars
        ]
        reference = float(observation.reference_price)
        observation.outcome_date = bars[-1].date
        observation.outcome_price = Decimal(str(prices[-1]))
        observation.return_pct = Decimal(str(round((prices[-1] / reference - 1) * 100, 6)))
        observation.max_adverse_pct = Decimal(str(round((min(prices) / reference - 1) * 100, 6)))
        observation.max_favorable_pct = Decimal(str(round((max(prices) / reference - 1) * 100, 6)))
        observation.status = "matured"
    await session.flush()

    return _calibration_out(workspace=workspace, observations=observations)


def _calibration_out(
    *,
    workspace: ResearchWorkspace,
    observations: list[ResearchOutcomeObservation],
) -> CalibrationOut:
    matured = [item for item in observations if item.status == "matured"]
    buckets = []
    for signal_status in ("qualified", "monitor", "rejected", "abstained"):
        for horizon in (5, 20, 60):
            rows = [
                item
                for item in matured
                if item.signal_status == signal_status and item.horizon_sessions == horizon
            ]
            if not rows:
                continue
            returns = [float(item.return_pct) for item in rows if item.return_pct is not None]
            buckets.append(
                {
                    "signalStatus": signal_status,
                    "horizonSessions": horizon,
                    "observations": len(returns),
                    "averageReturnPct": round(sum(returns) / len(returns), 3),
                    "positiveRatePct": round(
                        sum(value > 0 for value in returns) / len(returns) * 100, 1
                    ),
                }
            )
    return CalibrationOut(
        workspace_id=workspace.id,
        tenant_id=workspace.tenant_id,
        market=workspace.market,
        pending=sum(item.status == "pending" for item in observations),
        matured=len(matured),
        buckets=buckets,
        observations=[CalibrationObservationOut.from_record(item) for item in observations[:100]],
    )


async def load_outcome_calibration(
    session: AsyncSession, *, workspace: ResearchWorkspace
) -> CalibrationOut:
    """Read the persisted forward-outcome ledger without advancing it on GET."""

    observations = list(
        await session.scalars(
            select(ResearchOutcomeObservation)
            .where(
                ResearchOutcomeObservation.workspace_id == workspace.id,
                ResearchOutcomeObservation.organization_id == workspace.organization_id,
                ResearchOutcomeObservation.tenant_id == workspace.tenant_id,
                ResearchOutcomeObservation.market == workspace.market,
            )
            .order_by(ResearchOutcomeObservation.reference_date.desc())
        )
    )
    return _calibration_out(workspace=workspace, observations=observations)
