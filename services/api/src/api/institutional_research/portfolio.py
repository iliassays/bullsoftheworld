"""Atlas shadow-book persistence and forward calibration."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.institutional_research.investment import (
    get_active_mandate,
    mandate_snapshot,
    mark_trial_shadow,
    record_ladder_freeze_clearance,
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
    ShadowState,
    advance_shadow_portfolio,
    evaluate_shadow_promotion,
)
from bulls.core.models import (
    DailyBar,
    ResearchOutcomeObservation,
    ResearchShadowPortfolio,
    ResearchShadowSnapshot,
    ResearchStrategyTrial,
    ResearchWorkspace,
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
    backtest_request["universe_limit"] = max(5, min(30, len(observable_codes) or 5))
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
            "mandate": pinned_mandate,
            "mandate_binding": "pinned_at_inception",
        },
    )
    session.add(portfolio)
    initial_snapshot = ResearchShadowSnapshot(
        id=uuid.uuid4(),
        portfolio_id=portfolio.id,
        organization_id=workspace.organization_id,
        tenant_id=workspace.tenant_id,
        market=workspace.market,
        as_of_date=portfolio.inception_date,
        session_number=0,
        nav=initial_capital,
        cash=initial_capital,
        benchmark_nav=initial_capital,
        peak_nav=initial_capital,
        gross_exposure_pct=Decimal("0"),
        drawdown_pct=Decimal("0"),
        cumulative_fees=Decimal("0"),
        cumulative_turnover=Decimal("0"),
        positions={},
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
        previous = ShadowState(
            cash=float(latest.cash),
            positions=latest.positions,
            peak_nav=float(latest.peak_nav),
            benchmark_nav=float(latest.benchmark_nav),
            cumulative_fees=float(latest.cumulative_fees),
            cumulative_turnover=float(latest.cumulative_turnover),
            # The drawdown-ladder freeze is book-level state and must survive across refreshes,
            # otherwise a frozen book would silently re-arm on the next advance.
            ladder_frozen=bool(portfolio.configuration.get("ladder_frozen", False)),
        )
        advanced = advance_shadow_portfolio(
            market=portfolio.market,
            strategy_key=portfolio.strategy_key,
            securities=current_securities,
            previous=previous,
            target_weights={key: float(value) for key, value in latest.target_weights.items()},
            session_number=latest.session_number + 1,
            risk_policy=risk_policy,
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
            cash=Decimal(str(advanced.state.cash)),
            benchmark_nav=Decimal(str(advanced.state.benchmark_nav)),
            peak_nav=Decimal(str(advanced.state.peak_nav)),
            gross_exposure_pct=Decimal(str(advanced.gross_exposure_pct)),
            drawdown_pct=Decimal(str(advanced.drawdown_pct)),
            cumulative_fees=Decimal(str(advanced.state.cumulative_fees)),
            cumulative_turnover=Decimal(str(advanced.state.cumulative_turnover)),
            positions={
                code: position.model_dump(mode="json")
                for code, position in advanced.state.positions.items()
            },
            target_weights=advanced.next_target_weights,
            trades=[trade.model_dump(mode="json") for trade in advanced.trades],
            risk_interventions=[
                intervention.model_dump(mode="json") for intervention in advanced.risk_interventions
            ],
        )
        session.add(latest)
        portfolio.last_evaluated_on = advanced.date
        if bool(portfolio.configuration.get("ladder_frozen", False)) != advanced.state.ladder_frozen:
            portfolio.configuration = {
                **portfolio.configuration,
                "ladder_frozen": advanced.state.ladder_frozen,
            }
        await session.flush()
        await record_snapshot_decision_events(
            session,
            portfolio=portfolio,
            snapshot=latest,
            previous=previous_snapshot,
        )
    await _evaluate_portfolio_promotion(session, portfolio=portfolio)


async def clear_shadow_ladder_freeze(
    session: AsyncSession,
    *,
    workspace: ResearchWorkspace,
    portfolio_id: uuid.UUID,
    user_id: int,
    reason: str,
) -> ResearchShadowPortfolioOut:
    """Release a drawdown-ladder freeze after a written review (Phase 15 L2/L3.4).

    The ladder flattens and freezes a book on its own; only this deliberate, justified action can
    re-arm it. The reason is mandatory and is appended to the decision ledger as an override —
    silent erosion of the risk grammar is the documented failure mode we are guarding against.
    """
    written_reason = reason.strip()
    if not written_reason:
        raise ValueError("a written review reason is required to clear a drawdown-ladder freeze")

    portfolio = await session.scalar(
        select(ResearchShadowPortfolio).where(
            ResearchShadowPortfolio.id == portfolio_id,
            ResearchShadowPortfolio.workspace_id == workspace.id,
            ResearchShadowPortfolio.organization_id == workspace.organization_id,
            ResearchShadowPortfolio.tenant_id == workspace.tenant_id,
            ResearchShadowPortfolio.market == workspace.market,
        )
    )
    if portfolio is None:
        raise LookupError("shadow portfolio not found in this workspace")
    if not bool(portfolio.configuration.get("ladder_frozen", False)):
        raise ValueError("this shadow book is not frozen")

    snapshots = await _snapshots(session, portfolio=portfolio, limit=1)
    if not snapshots:
        raise ValueError("a frozen book cannot be cleared before it has a recorded snapshot")

    portfolio.configuration = {**portfolio.configuration, "ladder_frozen": False}
    await record_ladder_freeze_clearance(
        session,
        portfolio=portfolio,
        snapshot=snapshots[-1],
        user_id=user_id,
        reason=written_reason,
    )
    await session.flush()
    return await _portfolio_out(session, portfolio)


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
            select(ResearchShadowPortfolio).where(
                ResearchShadowPortfolio.workspace_id == workspace.id,
                ResearchShadowPortfolio.organization_id == workspace.organization_id,
                ResearchShadowPortfolio.tenant_id == workspace.tenant_id,
                ResearchShadowPortfolio.market == workspace.market,
                ResearchShadowPortfolio.status == "active",
            ).with_for_update()
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
