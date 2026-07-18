"""Atlas investment mandate, trial registry, decision audit, risk, and attribution."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.institutional_research.schemas import (
    DecisionEventOut,
    InvestmentMandateOut,
    InvestmentMandateUpdate,
    InvestmentOperatingViewOut,
    PerformanceAttributionOut,
    PortfolioOperatingAnalyticsOut,
    PortfolioRiskReportOut,
    StrategyTrialOut,
)
from bulls.analytics.portfolio_intelligence import (
    AttributionPoint,
    MandateLimits,
    PositionRiskInput,
    analyze_portfolio_risk,
    attribute_performance,
)
from bulls.analytics.research_strategy import (
    RISK_POLICIES,
    PortfolioRiskPolicy,
    StrategyDefinition,
)
from bulls.core.models import (
    DailyBar,
    ResearchDecisionEvent,
    ResearchInvestmentMandate,
    ResearchRun,
    ResearchShadowPortfolio,
    ResearchShadowSnapshot,
    ResearchStrategyTrial,
    ResearchWorkspace,
    Symbol,
)

_DEFAULT_OBJECTIVE = (
    "Capital preservation and benchmark-relative compounding through registered long-only "
    "strategies. Missing or stale evidence requires abstention."
)

_ECONOMIC_HYPOTHESES = {
    "dse_reversal_v1": (
        "Liquid DSE securities that suffered a material drawdown but show controlled short-term "
        "recovery and renewed participation may mean-revert as forced selling exhausts."
    ),
    "us_breakout_v1": (
        "Liquid US securities with persistent positive trend, participation confirmation, and "
        "limited extension may continue as slower capital adjusts to improving price information."
    ),
    "us_leader_capture_v1": (
        "US companies with accelerating reported revenue and improving earnings may compound "
        "while persistent price leadership reflects gradual institutional recognition; requiring "
        "both point-in-time filing evidence and trend confirmation aims to avoid narrative-only bets."
    ),
}


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def default_mandate_payload(market: str) -> InvestmentMandateUpdate:
    policy = RISK_POLICIES[market]
    return InvestmentMandateUpdate(
        objective=_DEFAULT_OBJECTIVE,
        benchmark_key=("dsex_equal_weight_proxy" if market == "DSE" else "us_equal_weight_proxy"),
        max_gross_exposure_pct=policy.max_gross_exposure * 100,
        min_cash_reserve_pct=(1 - policy.max_gross_exposure) * 100,
        max_position_weight_pct=policy.max_position_weight * 100,
        max_sector_weight_pct=policy.max_sector_weight * 100,
        max_adv_participation_pct=policy.max_adv_participation * 100,
        portfolio_drawdown_brake_pct=policy.portfolio_drawdown_brake * 100,
        stress_loss_limit_pct=12 if market == "DSE" else 15,
    )


def _mandate_values(payload: InvestmentMandateUpdate) -> dict[str, Any]:
    return payload.model_dump(mode="json")


def mandate_out(record: ResearchInvestmentMandate) -> InvestmentMandateOut:
    return InvestmentMandateOut(
        id=record.id,
        workspace_id=record.workspace_id,
        tenant_id=record.tenant_id,
        market=record.market,
        version=record.version,
        status=record.status,
        objective=record.objective,
        benchmark_key=record.benchmark_key,
        max_gross_exposure_pct=float(record.max_gross_exposure_pct),
        min_cash_reserve_pct=float(record.min_cash_reserve_pct),
        max_position_weight_pct=float(record.max_position_weight_pct),
        max_sector_weight_pct=float(record.max_sector_weight_pct),
        max_adv_participation_pct=float(record.max_adv_participation_pct),
        portfolio_drawdown_brake_pct=float(record.portfolio_drawdown_brake_pct),
        stress_loss_limit_pct=float(record.stress_loss_limit_pct),
        specification_hash=record.specification_hash,
        effective_at=record.effective_at,
        superseded_at=record.superseded_at,
    )


def mandate_snapshot(record: ResearchInvestmentMandate) -> dict[str, Any]:
    return mandate_out(record).model_dump(mode="json")


def risk_policy_from_mandate(record: ResearchInvestmentMandate) -> PortfolioRiskPolicy:
    """Apply mandate ceilings while retaining market-specific costs and stop assumptions."""

    return risk_policy_from_snapshot(mandate_snapshot(record), record.market)


def risk_policy_from_snapshot(value: dict[str, Any], market: str) -> PortfolioRiskPolicy:
    """Rehydrate the exact mandate pinned to a trial or shadow book."""

    mandate = InvestmentMandateOut.model_validate(value)
    if mandate.market != market:
        raise ValueError("pinned mandate belongs to another market")
    base = RISK_POLICIES[market]
    return base.model_copy(
        update={
            "max_adv_participation": mandate.max_adv_participation_pct / 100,
            "max_position_weight": mandate.max_position_weight_pct / 100,
            "max_sector_weight": mandate.max_sector_weight_pct / 100,
            "max_gross_exposure": mandate.max_gross_exposure_pct / 100,
            "portfolio_drawdown_brake": mandate.portfolio_drawdown_brake_pct / 100,
        }
    )


async def get_active_mandate(
    session: AsyncSession, *, workspace: ResearchWorkspace, lock: bool = False
) -> ResearchInvestmentMandate | None:
    statement = select(ResearchInvestmentMandate).where(
        ResearchInvestmentMandate.workspace_id == workspace.id,
        ResearchInvestmentMandate.organization_id == workspace.organization_id,
        ResearchInvestmentMandate.tenant_id == workspace.tenant_id,
        ResearchInvestmentMandate.market == workspace.market,
        ResearchInvestmentMandate.status == "active",
    )
    if lock:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def ensure_default_mandate(
    session: AsyncSession, *, workspace: ResearchWorkspace, user_id: int
) -> ResearchInvestmentMandate:
    current = await get_active_mandate(session, workspace=workspace, lock=True)
    if current is not None:
        return current
    payload = default_mandate_payload(workspace.market)
    values = _mandate_values(payload)
    record = ResearchInvestmentMandate(
        id=uuid.uuid4(),
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        tenant_id=workspace.tenant_id,
        market=workspace.market,
        created_by_user_id=user_id,
        version=1,
        status="active",
        specification_hash=_hash(values),
        effective_at=dt.datetime.now(dt.UTC),
        **values,
    )
    session.add(record)
    await session.flush()
    return record


async def replace_active_mandate(
    session: AsyncSession,
    *,
    workspace: ResearchWorkspace,
    user_id: int,
    payload: InvestmentMandateUpdate,
) -> InvestmentMandateOut:
    expected_benchmark = default_mandate_payload(workspace.market).benchmark_key
    if payload.benchmark_key != expected_benchmark:
        raise ValueError(
            f"{workspace.market} currently supports only the measured benchmark "
            f"{expected_benchmark}"
        )
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
    current = await get_active_mandate(session, workspace=workspace, lock=True)
    now = dt.datetime.now(dt.UTC)
    version = 1
    if current is not None:
        current.status = "superseded"
        current.superseded_at = now
        version = current.version + 1
        await session.flush()
    values = _mandate_values(payload)
    replacement = ResearchInvestmentMandate(
        id=uuid.uuid4(),
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        tenant_id=workspace.tenant_id,
        market=workspace.market,
        created_by_user_id=user_id,
        version=version,
        status="active",
        specification_hash=_hash(values),
        effective_at=now,
        **values,
    )
    session.add(replacement)
    await session.flush()
    return mandate_out(replacement)


def _trial_out(record: ResearchStrategyTrial) -> StrategyTrialOut:
    return StrategyTrialOut(
        id=record.id,
        source_run_id=record.source_run_id,
        workspace_id=record.workspace_id,
        tenant_id=record.tenant_id,
        market=record.market,
        strategy_key=record.strategy_key,
        strategy_version=record.strategy_version,
        status=record.status,
        registration_state=record.registration_state,
        trial_sequence=record.trial_sequence,
        multiple_testing_policy=record.multiple_testing_policy,
        economic_hypothesis=record.economic_hypothesis,
        specification=record.specification,
        specification_hash=record.specification_hash,
        outcome=record.outcome,
        registered_at=record.registered_at,
        completed_at=record.completed_at,
    )


async def register_strategy_trial(
    session: AsyncSession,
    *,
    workspace: ResearchWorkspace,
    run: ResearchRun,
    user_id: int,
    strategy: StrategyDefinition,
    specification: dict[str, Any],
) -> ResearchStrategyTrial:
    # Serialize family numbering even when two experiment requests arrive concurrently.
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
    prior_trials = await session.scalar(
        select(func.count(ResearchStrategyTrial.id)).where(
            ResearchStrategyTrial.workspace_id == workspace.id,
            ResearchStrategyTrial.organization_id == workspace.organization_id,
            ResearchStrategyTrial.tenant_id == workspace.tenant_id,
            ResearchStrategyTrial.market == workspace.market,
            ResearchStrategyTrial.strategy_key == strategy.key,
        )
    )
    trial = ResearchStrategyTrial(
        id=uuid.uuid4(),
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        tenant_id=workspace.tenant_id,
        market=workspace.market,
        source_run_id=run.id,
        created_by_user_id=user_id,
        strategy_key=strategy.key,
        strategy_version=strategy.methodology_version,
        status="registered",
        registration_state="preregistered",
        trial_sequence=int(prior_trials or 0) + 1,
        multiple_testing_policy="family_gate_v1",
        economic_hypothesis=_ECONOMIC_HYPOTHESES[strategy.key],
        specification=specification,
        specification_hash=_hash(specification),
        outcome={},
        registered_at=dt.datetime.now(dt.UTC),
    )
    session.add(trial)
    await session.flush()
    return trial


async def complete_strategy_trial(
    session: AsyncSession,
    *,
    trial: ResearchStrategyTrial,
    validation_status: str,
    outcome: dict[str, Any],
) -> None:
    trial.status = "diagnostic" if validation_status != "eligible_for_shadow" else "registered"
    trial.outcome = outcome
    trial.completed_at = dt.datetime.now(dt.UTC)
    await session.flush()


async def mark_trial_shadow(
    session: AsyncSession, *, source_run_id: uuid.UUID, workspace: ResearchWorkspace
) -> None:
    trial = await session.scalar(
        select(ResearchStrategyTrial).where(
            ResearchStrategyTrial.source_run_id == source_run_id,
            ResearchStrategyTrial.workspace_id == workspace.id,
            ResearchStrategyTrial.organization_id == workspace.organization_id,
            ResearchStrategyTrial.tenant_id == workspace.tenant_id,
            ResearchStrategyTrial.market == workspace.market,
        )
    )
    if trial is not None:
        trial.status = "shadow"
        await session.flush()


async def list_strategy_trials(
    session: AsyncSession, *, workspace: ResearchWorkspace
) -> list[StrategyTrialOut]:
    records = list(
        await session.scalars(
            select(ResearchStrategyTrial)
            .where(
                ResearchStrategyTrial.workspace_id == workspace.id,
                ResearchStrategyTrial.organization_id == workspace.organization_id,
                ResearchStrategyTrial.tenant_id == workspace.tenant_id,
                ResearchStrategyTrial.market == workspace.market,
            )
            .order_by(ResearchStrategyTrial.registered_at.desc())
            .limit(100)
        )
    )
    return [_trial_out(record) for record in records]


def _target_changes(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for code in sorted(set(previous) | set(current)):
        before = float(previous.get(code, 0))
        after = float(current.get(code, 0))
        if abs(before - after) < 1e-9:
            continue
        action = (
            "entry"
            if before == 0 and after > 0
            else "exit"
            if before > 0 and after == 0
            else "increase"
            if after > before
            else "reduce"
        )
        changes.append(
            {"code": code, "previous_weight": before, "target_weight": after, "action": action}
        )
    return changes


async def record_snapshot_decision_events(
    session: AsyncSession,
    *,
    portfolio: ResearchShadowPortfolio,
    snapshot: ResearchShadowSnapshot,
    previous: ResearchShadowSnapshot | None,
) -> None:
    """Append an idempotent audit projection derived from one accepted shadow snapshot.

    These events explain the snapshot but do not replace the independent accounting ledger.
    """

    existing_keys = set(
        await session.scalars(
            select(ResearchDecisionEvent.event_key).where(
                ResearchDecisionEvent.portfolio_id == portfolio.id,
                ResearchDecisionEvent.snapshot_id == snapshot.id,
                ResearchDecisionEvent.organization_id == portfolio.organization_id,
                ResearchDecisionEvent.tenant_id == portfolio.tenant_id,
                ResearchDecisionEvent.market == portfolio.market,
            )
        )
    )
    maximum_sequence = await session.scalar(
        select(func.max(ResearchDecisionEvent.sequence)).where(
            ResearchDecisionEvent.portfolio_id == portfolio.id,
            ResearchDecisionEvent.organization_id == portfolio.organization_id,
            ResearchDecisionEvent.tenant_id == portfolio.tenant_id,
            ResearchDecisionEvent.market == portfolio.market,
        )
    )
    sequence = int(maximum_sequence) + 1 if maximum_sequence is not None else 0
    correlation_id = uuid.uuid5(portfolio.id, f"snapshot:{snapshot.id}")
    events: list[dict[str, Any]] = []

    def append(
        key: str,
        event_type: str,
        state: str,
        payload: dict[str, Any],
        *,
        code: str | None = None,
        caused_by: str | None = None,
    ) -> None:
        if key in existing_keys:
            return
        events.append(
            {
                "event_key": key,
                "event_type": event_type,
                "event_state": state,
                "payload": payload,
                "code": code,
                "caused_by_event_key": caused_by,
            }
        )

    prior_target_events = list(
        await session.scalars(
            select(ResearchDecisionEvent)
            .where(
                ResearchDecisionEvent.portfolio_id == portfolio.id,
                ResearchDecisionEvent.event_type == "target",
                ResearchDecisionEvent.organization_id == portfolio.organization_id,
                ResearchDecisionEvent.tenant_id == portfolio.tenant_id,
                ResearchDecisionEvent.market == portfolio.market,
                ResearchDecisionEvent.effective_date < snapshot.as_of_date,
            )
            .order_by(ResearchDecisionEvent.sequence.desc())
        )
    )
    latest_target_by_code: dict[str, str] = {}
    for event in prior_target_events:
        if event.code and event.code not in latest_target_by_code:
            latest_target_by_code[event.code] = event.event_key

    risk_target_causes: dict[str, str] = {}
    portfolio_target_cause: str | None = None
    for index, intervention in enumerate(snapshot.risk_interventions):
        code_value = intervention.get("code")
        code = str(code_value).upper() if code_value else None
        rule = str(intervention.get("rule", "unknown"))
        event_type = (
            "rejection" if rule in {"cash_limit", "missing_bar", "liquidity_unknown"} else "risk"
        )
        event_key = f"s{snapshot.session_number}:{event_type}:{index}:{code or 'portfolio'}:{rule}"
        append(
            event_key,
            event_type,
            "constrained",
            intervention,
            code=code,
            caused_by=latest_target_by_code.get(code) if code else None,
        )
        if rule == "position_stop" and code:
            risk_target_causes[code] = event_key
        elif rule == "portfolio_drawdown_brake":
            portfolio_target_cause = event_key

    prior_targets = previous.target_weights if previous is not None else {}
    for change in _target_changes(prior_targets, snapshot.target_weights):
        code = change["code"]
        target_key = f"s{snapshot.session_number}:target:{code}:{change['action']}"
        risk_cause = risk_target_causes.get(code)
        if change["action"] in {"exit", "reduce"} and portfolio_target_cause is not None:
            risk_cause = risk_cause or portfolio_target_cause
        if risk_cause is not None:
            append(
                target_key,
                "target",
                "intended",
                {**change, "origin": "risk_policy"},
                code=code,
                caused_by=risk_cause,
            )
            continue
        signal_key = f"s{snapshot.session_number}:signal:{code}:{change['action']}"
        append(
            signal_key,
            "signal",
            "observed",
            {
                "strategy_key": portfolio.strategy_key,
                "source_run_id": str(portfolio.source_run_id),
                "qualification": change["action"],
                "knowledge_date": snapshot.as_of_date.isoformat(),
            },
            code=code,
        )
        append(
            target_key,
            "target",
            "intended",
            {**change, "origin": "strategy"},
            code=code,
            caused_by=signal_key,
        )

    for index, trade in enumerate(snapshot.trades):
        code = str(trade.get("code", "")).upper()
        order_key = f"s{snapshot.session_number}:order:{index}:{code}"
        fill_key = f"s{snapshot.session_number}:fill:{index}:{code}"
        append(
            order_key,
            "order",
            "intended",
            {
                "side": trade.get("side"),
                "requested_quantity": trade.get("intended_quantity", trade.get("quantity")),
                "execution_model": "next_observable_open_with_costs",
            },
            code=code,
            caused_by=latest_target_by_code.get(code),
        )
        append(fill_key, "fill", "executed", trade, code=code, caused_by=order_key)

    before_positions = previous.positions if previous is not None else {}
    for code in sorted(set(before_positions) | set(snapshot.positions)):
        before = before_positions.get(code)
        after = snapshot.positions.get(code)
        if before == after:
            continue
        position_state = "closed" if after is None else "open"
        related_fill = next(
            (
                f"s{snapshot.session_number}:fill:{index}:{code}"
                for index, trade in enumerate(snapshot.trades)
                if str(trade.get("code", "")).upper() == code
            ),
            None,
        )
        append(
            f"s{snapshot.session_number}:position:{code}:{position_state}",
            "position",
            position_state,
            {"before": before, "after": after},
            code=code,
            caused_by=related_fill,
        )

    append(
        f"s{snapshot.session_number}:outcome",
        "outcome",
        "measured",
        {
            "projection_role": "snapshot_audit_only",
            "nav": float(snapshot.nav),
            "benchmark_nav": float(snapshot.benchmark_nav),
            "cash": float(snapshot.cash),
            "gross_exposure_pct": float(snapshot.gross_exposure_pct),
            "drawdown_pct": float(snapshot.drawdown_pct),
            "cumulative_fees": float(snapshot.cumulative_fees),
        },
    )

    for offset, event in enumerate(events):
        payload = event.pop("payload")
        session.add(
            ResearchDecisionEvent(
                id=uuid.uuid4(),
                organization_id=portfolio.organization_id,
                workspace_id=portfolio.workspace_id,
                tenant_id=portfolio.tenant_id,
                market=portfolio.market,
                portfolio_id=portfolio.id,
                snapshot_id=snapshot.id,
                correlation_id=correlation_id,
                sequence=sequence + offset,
                effective_date=snapshot.as_of_date,
                payload=payload,
                payload_hash=_hash(payload),
                **event,
            )
        )
    await session.flush()


def _decision_event_out(record: ResearchDecisionEvent) -> DecisionEventOut:
    return DecisionEventOut(
        id=record.id,
        portfolio_id=record.portfolio_id,
        snapshot_id=record.snapshot_id,
        correlation_id=record.correlation_id,
        sequence=record.sequence,
        event_key=record.event_key,
        caused_by_event_key=record.caused_by_event_key,
        event_type=record.event_type,
        event_state=record.event_state,
        code=record.code,
        effective_date=record.effective_date,
        payload=record.payload,
        payload_hash=record.payload_hash,
        recorded_at=record.recorded_at,
    )


def _limits_from_snapshot(
    value: dict[str, Any],
    fallback: ResearchInvestmentMandate,
    binding_origin: str | None,
) -> tuple[
    MandateLimits,
    InvestmentMandateOut,
    Literal["pinned", "legacy_active_fallback"],
]:
    try:
        mandate = InvestmentMandateOut.model_validate(value)
        binding: Literal["pinned", "legacy_active_fallback"] = (
            "pinned" if binding_origin == "pinned_at_inception" else "legacy_active_fallback"
        )
    except (TypeError, ValidationError):
        mandate = mandate_out(fallback)
        binding = "legacy_active_fallback"
    return (
        MandateLimits(
            market=mandate.market,
            benchmark_key=mandate.benchmark_key,
            max_gross_exposure_pct=mandate.max_gross_exposure_pct,
            min_cash_reserve_pct=mandate.min_cash_reserve_pct,
            max_position_weight_pct=mandate.max_position_weight_pct,
            max_sector_weight_pct=mandate.max_sector_weight_pct,
            max_adv_participation_pct=mandate.max_adv_participation_pct,
            portfolio_drawdown_brake_pct=mandate.portfolio_drawdown_brake_pct,
            stress_loss_limit_pct=mandate.stress_loss_limit_pct,
        ),
        mandate,
        binding,
    )


async def _position_risk_inputs(
    session: AsyncSession,
    *,
    portfolio: ResearchShadowPortfolio,
    snapshot: ResearchShadowSnapshot,
) -> tuple[list[PositionRiskInput], list[str]]:
    codes = sorted(snapshot.positions)
    if not codes:
        return [], []
    sectors = dict(
        (
            await session.execute(
                select(Symbol.code, Symbol.sector).where(
                    Symbol.market == portfolio.market,
                    Symbol.code.in_(codes),
                )
            )
        ).all()
    )
    bars = list(
        await session.scalars(
            select(DailyBar)
            .where(
                DailyBar.market == portfolio.market,
                DailyBar.code.in_(codes),
                DailyBar.date <= snapshot.as_of_date,
                DailyBar.date >= snapshot.as_of_date - dt.timedelta(days=140),
            )
            .order_by(DailyBar.code, DailyBar.date)
        )
    )
    by_code: dict[str, list[DailyBar]] = {code: [] for code in codes}
    for bar in bars:
        by_code.setdefault(bar.code, []).append(bar)
    inputs: list[PositionRiskInput] = []
    unavailable_codes: list[str] = []
    for code in codes:
        position = snapshot.positions[code]
        shares = int(position.get("shares", 0))
        if shares <= 0:
            continue
        history = by_code.get(code, [])
        if not history or history[-1].date != snapshot.as_of_date:
            unavailable_codes.append(code)
            continue
        closes = [
            float(bar.adjusted_close if bar.adjusted_close is not None else bar.close)
            for bar in history
        ]
        returns = [
            closes[index] / closes[index - 1] - 1
            for index in range(1, len(closes))
            if closes[index - 1] > 0
        ]
        return_observations = {
            history[index].date: closes[index] / closes[index - 1] - 1
            for index in range(1, len(closes))
            if closes[index - 1] > 0
        }
        volumes = [float(bar.volume) for bar in history[-20:] if bar.volume > 0]
        inputs.append(
            PositionRiskInput(
                code=code,
                sector=sectors.get(code) or "Unclassified",
                shares=shares,
                price=closes[-1],
                average_daily_volume=(sum(volumes) / len(volumes) if volumes else None),
                returns=returns,
                return_observations=return_observations,
            )
        )
    return inputs, unavailable_codes


async def load_investment_operating_view(
    session: AsyncSession, *, workspace: ResearchWorkspace
) -> InvestmentOperatingViewOut:
    mandate_record = await get_active_mandate(session, workspace=workspace)
    if mandate_record is None:
        raise RuntimeError("The workspace has no active investment mandate")
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
    analytics: list[PortfolioOperatingAnalyticsOut] = []
    for portfolio in portfolios:
        snapshots = list(
            await session.scalars(
                select(ResearchShadowSnapshot)
                .where(
                    ResearchShadowSnapshot.portfolio_id == portfolio.id,
                    ResearchShadowSnapshot.organization_id == workspace.organization_id,
                    ResearchShadowSnapshot.tenant_id == workspace.tenant_id,
                    ResearchShadowSnapshot.market == workspace.market,
                )
                .order_by(ResearchShadowSnapshot.as_of_date)
                .limit(5000)
            )
        )
        latest = snapshots[-1] if snapshots else None
        limits, pinned_mandate, binding = _limits_from_snapshot(
            portfolio.configuration.get("mandate", {}),
            mandate_record,
            (
                portfolio.configuration.get("mandate_binding")
                if isinstance(portfolio.configuration.get("mandate_binding"), str)
                else None
            ),
        )
        inputs, unavailable_position_codes = (
            await _position_risk_inputs(session, portfolio=portfolio, snapshot=latest)
            if latest is not None
            else ([], [])
        )
        risk = analyze_portfolio_risk(
            nav=float(latest.nav) if latest else float(portfolio.initial_capital),
            cash=float(latest.cash) if latest else float(portfolio.initial_capital),
            drawdown_pct=float(latest.drawdown_pct) if latest else 0,
            positions=inputs,
            mandate=limits,
            unavailable_position_codes=unavailable_position_codes,
        )
        events = list(
            await session.scalars(
                select(ResearchDecisionEvent)
                .where(
                    ResearchDecisionEvent.portfolio_id == portfolio.id,
                    ResearchDecisionEvent.organization_id == workspace.organization_id,
                    ResearchDecisionEvent.tenant_id == workspace.tenant_id,
                    ResearchDecisionEvent.market == workspace.market,
                )
                .order_by(ResearchDecisionEvent.sequence.desc())
                .limit(200)
            )
        )
        rejected_actions = sum(event.event_type == "rejection" for event in events)
        if not events:
            rejected_actions = sum(len(item.risk_interventions) for item in snapshots)
        attribution = attribute_performance(
            [
                AttributionPoint(
                    nav=float(item.nav),
                    benchmark_nav=float(item.benchmark_nav),
                    gross_exposure_pct=float(item.gross_exposure_pct),
                    cumulative_fees=float(item.cumulative_fees),
                )
                for item in snapshots
            ],
            rejected_actions=rejected_actions,
        )
        notes = list(risk.data_quality_notes)
        if binding == "legacy_active_fallback":
            notes.append(
                "This legacy book predates mandate pinning; analytics use the current active mandate."
            )
            risk = risk.model_copy(update={"data_quality_notes": notes})
        analytics.append(
            PortfolioOperatingAnalyticsOut(
                portfolio_id=portfolio.id,
                as_of_date=latest.as_of_date if latest else None,
                mandate=pinned_mandate,
                mandate_version=pinned_mandate.version,
                mandate_binding=binding,
                risk=PortfolioRiskReportOut.model_validate(risk.model_dump()),
                attribution=PerformanceAttributionOut.model_validate(attribution.model_dump()),
                recent_events=[_decision_event_out(event) for event in events],
            )
        )
    return InvestmentOperatingViewOut(
        workspace_id=workspace.id,
        tenant_id=workspace.tenant_id,
        market=workspace.market,
        generated_at=dt.datetime.now(dt.UTC),
        mandate=mandate_out(mandate_record),
        trials=await list_strategy_trials(session, workspace=workspace),
        portfolios=analytics,
    )
