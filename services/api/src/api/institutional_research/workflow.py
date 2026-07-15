"""Durable autonomous research and point-in-time experiment orchestration."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.institutional_research.dossier import build_company_dossier
from api.institutional_research.schemas import BacktestRequest, ResearchRunOut
from bulls.analytics.research_loop import (
    METHODOLOGY_VERSION,
    AutonomousResearchInput,
    ResearchFact,
    run_autonomous_research,
)
from bulls.analytics.research_strategy import (
    ENGINE_VERSION,
    StrategyBar,
    StrategySecurity,
    run_backtest,
)
from bulls.core.models import (
    DailyBar,
    ResearchClaim,
    ResearchOutcomeObservation,
    ResearchRun,
    ResearchRunStep,
    ResearchWorkspace,
    Symbol,
    TickerAnalytics,
)


def _utc(value: dt.datetime) -> dt.datetime:
    return value.replace(tzinfo=dt.UTC) if value.tzinfo is None else value.astimezone(dt.UTC)


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _fact(
    key: str,
    value: Any,
    *,
    cutoff: dt.datetime,
    source_kind: str = "calculation",
    source_id: str | None = None,
    unit: str | None = None,
) -> ResearchFact:
    return ResearchFact(
        key=key,
        label=key.replace("_", " ").title(),
        value=value,
        unit=unit,
        as_of=cutoff.isoformat(),
        source_kind=source_kind,
        source_id=source_id or f"calculation:{key}",
    )


def _research_input(dossier) -> AutonomousResearchInput:
    candidate = dossier.candidate
    details = candidate.factor_details
    cutoff = dossier.knowledge_cutoff_at
    quality_inputs = details.quality.inputs
    value_inputs = details.value.inputs
    momentum_inputs = details.momentum.inputs
    risk_inputs = details.risk.inputs
    latest_evidence = candidate.evidence.items[0] if candidate.evidence.items else None
    facts = [
        _fact("quality_score", candidate.factors.quality, cutoff=cutoff),
        _fact("value_score", candidate.factors.value, cutoff=cutoff),
        _fact("momentum_score", candidate.factors.momentum, cutoff=cutoff),
        _fact("risk_score", candidate.factors.risk, cutoff=cutoff),
        _fact("evidence_coverage", candidate.evidence.coverage_pct, cutoff=cutoff, unit="pct"),
        _fact("cap_tier", candidate.cap_tier, cutoff=cutoff, source_kind="market_data"),
        _fact("last_price", candidate.price, cutoff=cutoff, source_kind="market_data"),
        _fact(
            "market_cap_mn",
            dossier.market_data.market_cap_mn,
            cutoff=cutoff,
            source_kind="market_data",
            unit="mn",
        ),
        _fact(
            "average_daily_value_mn",
            risk_inputs.get("average_daily_value_mn"),
            cutoff=cutoff,
            source_kind="market_data",
            unit="mn",
        ),
        _fact(
            "volatility_pct",
            dossier.market_data.volatility_pct,
            cutoff=cutoff,
            source_kind="market_data",
            unit="pct",
        ),
        _fact(
            "relative_volume",
            dossier.market_data.relative_volume,
            cutoff=cutoff,
            source_kind="market_data",
            unit="x",
        ),
        _fact(
            "rsi_14",
            dossier.market_data.rsi_14,
            cutoff=cutoff,
            source_kind="market_data",
        ),
        _fact(
            "nearest_support",
            dossier.market_data.nearest_support,
            cutoff=cutoff,
            source_kind="market_data",
        ),
        _fact(
            "nearest_resistance",
            dossier.market_data.nearest_resistance,
            cutoff=cutoff,
            source_kind="market_data",
        ),
        _fact("roe_pct", quality_inputs.get("roe_pct"), cutoff=cutoff, unit="pct"),
        _fact(
            "eps_growth_yoy_pct",
            quality_inputs.get("eps_growth_yoy_pct"),
            cutoff=cutoff,
            unit="pct",
        ),
        _fact("pe_ratio", value_inputs.get("pe_ratio"), cutoff=cutoff, unit="x"),
        _fact("pb_ratio", value_inputs.get("pb_ratio"), cutoff=cutoff, unit="x"),
        _fact("pe_vs_sector", value_inputs.get("pe_vs_sector"), cutoff=cutoff, unit="x"),
        _fact(
            "dividend_yield_pct",
            value_inputs.get("dividend_yield_pct"),
            cutoff=cutoff,
            unit="pct",
        ),
        _fact(
            "mom_3_1_pct",
            momentum_inputs.get("mom_3_1_pct"),
            cutoff=cutoff,
            source_kind="market_data",
            unit="pct",
        ),
        _fact(
            "mom_6_1_pct",
            momentum_inputs.get("mom_6_1_pct"),
            cutoff=cutoff,
            source_kind="market_data",
            unit="pct",
        ),
        _fact(
            "mom_12_1_pct",
            momentum_inputs.get("mom_12_1_pct"),
            cutoff=cutoff,
            source_kind="market_data",
            unit="pct",
        ),
        _fact(
            "above_sma_50",
            momentum_inputs.get("above_sma_50"),
            cutoff=cutoff,
            source_kind="market_data",
        ),
        _fact(
            "above_sma_200",
            momentum_inputs.get("above_sma_200"),
            cutoff=cutoff,
            source_kind="market_data",
        ),
    ]
    if latest_evidence is not None:
        facts.append(
            _fact(
                "latest_official_evidence",
                latest_evidence.title,
                cutoff=cutoff,
                source_kind="official_evidence",
                source_id=latest_evidence.id,
            )
        )
        facts.append(
            _fact(
                "latest_official_evidence_date",
                latest_evidence.published_at.isoformat(),
                cutoff=cutoff,
                source_kind="official_evidence",
                source_id=latest_evidence.id,
            )
        )
    if dossier.reported_ownership is not None:
        ownership = dossier.reported_ownership
        categories = {category.key: category for category in ownership.categories}
        institutional = categories.get("institutional")
        source_id = f"dse-ownership:{candidate.ticker}:{ownership.as_of_date}"
        facts.extend(
            [
                _fact(
                    "ownership_as_of_date",
                    ownership.as_of_date.isoformat(),
                    cutoff=cutoff,
                    source_kind="official_evidence",
                    source_id=source_id,
                ),
                _fact(
                    "institutional_ownership_pct",
                    institutional.value_pct if institutional else None,
                    cutoff=cutoff,
                    source_kind="official_evidence",
                    source_id=source_id,
                    unit="pct",
                ),
                _fact(
                    "institutional_ownership_change_pp",
                    institutional.change_pp if institutional else None,
                    cutoff=cutoff,
                    source_kind="official_evidence",
                    source_id=source_id,
                    unit="pp",
                ),
            ]
        )
    if dossier.institutional_disclosure is not None:
        disclosure = dossier.institutional_disclosure
        source_id = f"sec-13f:{candidate.ticker}:{disclosure.report_date}"
        facts.extend(
            [
                _fact(
                    "13f_report_date",
                    disclosure.report_date.isoformat(),
                    cutoff=cutoff,
                    source_kind="official_evidence",
                    source_id=source_id,
                ),
                _fact(
                    "13f_manager_count",
                    disclosure.managers_count,
                    cutoff=cutoff,
                    source_kind="official_evidence",
                    source_id=source_id,
                ),
                _fact(
                    "13f_net_breadth_pct",
                    disclosure.net_breadth_pct,
                    cutoff=cutoff,
                    source_kind="official_evidence",
                    source_id=source_id,
                    unit="pct",
                ),
                _fact(
                    "13f_net_change_pct",
                    disclosure.net_change_pct,
                    cutoff=cutoff,
                    source_kind="official_evidence",
                    source_id=source_id,
                    unit="pct",
                ),
            ]
        )
    if dossier.short_activity is not None:
        activity = dossier.short_activity
        source_id = f"finra-short-volume:{candidate.ticker}:{activity.as_of_date}"
        facts.extend(
            [
                _fact(
                    "finra_short_marked_share_pct",
                    activity.short_marked_share_pct,
                    cutoff=cutoff,
                    source_kind="official_evidence",
                    source_id=source_id,
                    unit="pct",
                ),
                _fact(
                    "finra_average_20_pct",
                    activity.average_20_pct,
                    cutoff=cutoff,
                    source_kind="official_evidence",
                    source_id=source_id,
                    unit="pct",
                ),
                _fact(
                    "finra_activity_vs_20x",
                    activity.activity_vs_20x,
                    cutoff=cutoff,
                    source_kind="official_evidence",
                    source_id=source_id,
                    unit="x",
                ),
            ]
        )
    return AutonomousResearchInput(
        market=dossier.market,
        code=candidate.ticker,
        company=candidate.company,
        knowledge_cutoff_at=cutoff.isoformat(),
        quality=candidate.factors.quality,
        value=candidate.factors.value,
        momentum=candidate.factors.momentum,
        risk=candidate.factors.risk,
        novelty=details.novelty.value,
        quality_confidence=details.quality.confidence,
        value_confidence=details.value.confidence,
        momentum_confidence=details.momentum.confidence,
        risk_confidence=details.risk.confidence,
        evidence_coverage_pct=candidate.evidence.coverage_pct,
        official_evidence_count=candidate.evidence.source_count,
        average_daily_value_mn=(
            float(risk_inputs["average_daily_value_mn"])
            if risk_inputs.get("average_daily_value_mn") is not None
            else None
        ),
        capacity_mn=None,
        cap_tier=candidate.cap_tier,
        flags=candidate.flags,
        facts=facts,
    )


async def _existing_run(
    session: AsyncSession, *, workspace: ResearchWorkspace, idempotency_key: str
) -> ResearchRun | None:
    return await session.scalar(
        select(ResearchRun).where(
            ResearchRun.workspace_id == workspace.id,
            ResearchRun.organization_id == workspace.organization_id,
            ResearchRun.tenant_id == workspace.tenant_id,
            ResearchRun.market == workspace.market,
            ResearchRun.idempotency_key == idempotency_key,
        )
    )


def _new_run(
    *,
    workspace: ResearchWorkspace,
    user_id: int,
    run_kind: str,
    question: str,
    code: str | None,
    parameters: dict[str, Any],
    idempotency_key: str,
    cutoff: dt.datetime,
    code_version: str,
    model: str = "provider-free",
) -> ResearchRun:
    return ResearchRun(
        id=uuid.uuid4(),
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        tenant_id=workspace.tenant_id,
        requested_by_user_id=user_id,
        run_kind=run_kind,
        status="running",
        question=question,
        market=workspace.market,
        code=code,
        parameters=parameters,
        idempotency_key=idempotency_key,
        knowledge_cutoff_at=cutoff,
        provider="deterministic",
        model=model,
        prompt_version=None,
        code_version=code_version,
        started_at=dt.datetime.now(dt.UTC),
    )


async def _persist_run_parent(session: AsyncSession, run: ResearchRun) -> None:
    """Make the parent visible before forced-RLS lineage policies validate child rows."""

    session.add(run)
    await session.flush()


def _add_step(
    session: AsyncSession,
    *,
    run: ResearchRun,
    ordinal: int,
    kind: str,
    output: dict[str, Any],
    metrics: dict[str, Any] | None = None,
    status: str = "succeeded",
    error_code: str | None = None,
) -> None:
    now = dt.datetime.now(dt.UTC)
    session.add(
        ResearchRunStep(
            id=uuid.uuid4(),
            organization_id=run.organization_id,
            run_id=run.id,
            tenant_id=run.tenant_id,
            market=run.market,
            ordinal=ordinal,
            step_kind=kind,
            status=status,
            input_hash=_stable_hash({"run": str(run.id), "ordinal": ordinal, "kind": kind}),
            output=output,
            metrics=metrics or {},
            started_at=now,
            completed_at=now,
            error_code=error_code,
        )
    )


async def execute_company_research(
    session: AsyncSession,
    *,
    workspace: ResearchWorkspace,
    user_id: int,
    code: str,
    idempotency_key: str,
) -> ResearchRunOut:
    existing = await _existing_run(session, workspace=workspace, idempotency_key=idempotency_key)
    if existing is not None:
        return await load_research_run(session, workspace=workspace, run_id=existing.id)

    dossier = await build_company_dossier(
        session,
        tenant_id=workspace.tenant_id,
        market=workspace.market,
        workspace_id=workspace.id,
        code=code,
    )
    payload = _research_input(dossier)
    result = run_autonomous_research(payload)
    run = _new_run(
        workspace=workspace,
        user_id=user_id,
        run_kind="deep_research",
        question=f"Form and challenge a bounded research thesis for {payload.code}.",
        code=payload.code,
        parameters={"methodology_version": METHODOLOGY_VERSION},
        idempotency_key=idempotency_key,
        cutoff=_utc(dossier.knowledge_cutoff_at),
        code_version=METHODOLOGY_VERSION,
        model="finance-reasoner-v2",
    )
    run.evidence_snapshot_hash = result.evidence_fingerprint
    await _persist_run_parent(session, run)
    facts_by_key = {fact.key: fact for fact in payload.facts}
    for stage in result.stages:
        _add_step(
            session,
            run=run,
            ordinal=stage.ordinal,
            kind=stage.kind,
            output=stage.model_dump(mode="json"),
        )
    for ordinal, claim in enumerate(result.claims):
        session.add(
            ResearchClaim(
                id=uuid.uuid4(),
                organization_id=run.organization_id,
                tenant_id=run.tenant_id,
                market=run.market,
                run_id=run.id,
                ordinal=ordinal,
                claim_type=claim.side,
                statement=claim.statement,
                verdict=claim.verdict,
                confidence=Decimal(str(claim.confidence)),
                as_of_at=run.knowledge_cutoff_at,
                values={
                    "key": claim.key,
                    "fact_keys": claim.fact_keys,
                    "facts": [
                        facts_by_key[key].model_dump(mode="json")
                        for key in claim.fact_keys
                        if key in facts_by_key
                    ],
                },
                verification={"summary": claim.verification, "rule": claim.rule},
            )
        )
    for horizon in (5, 20, 60):
        session.add(
            ResearchOutcomeObservation(
                id=uuid.uuid4(),
                organization_id=run.organization_id,
                workspace_id=run.workspace_id,
                tenant_id=run.tenant_id,
                market=run.market,
                run_id=run.id,
                code=payload.code,
                signal_status=result.status,
                confidence=Decimal(str(result.confidence)),
                reference_date=dossier.market_data.as_of_date,
                reference_price=Decimal(str(dossier.candidate.price)),
                horizon_sessions=horizon,
                status="pending",
            )
        )
    run.parameters = {
        **run.parameters,
        "decision": result.model_dump(mode="json", exclude={"stages", "claims"}),
    }
    run.status = "succeeded"
    run.completed_at = dt.datetime.now(dt.UTC)
    await session.flush()
    return await load_research_run(session, workspace=workspace, run_id=run.id)


async def _backtest_universe(
    session: AsyncSession,
    *,
    market: str,
    request: BacktestRequest,
) -> list[StrategySecurity]:
    end_date = request.end_date or await session.scalar(
        select(func.max(DailyBar.date)).where(DailyBar.market == market)
    )
    if end_date is None:
        return []
    start_date = request.start_date or (end_date - dt.timedelta(days=365 * 3 + 30))
    conditions = [
        Symbol.market == market,
        Symbol.is_active.is_(True),
        Symbol.is_hidden.is_(False),
        Symbol.data_status.in_(("ready", "research_only")),
        TickerAnalytics.market == market,
    ]
    if request.codes:
        conditions.append(Symbol.code.in_([code.upper() for code in request.codes]))
    if request.cap_tier:
        conditions.append(TickerAnalytics.cap_tier == request.cap_tier)
    rows = (
        await session.execute(
            select(Symbol, TickerAnalytics)
            .join(
                TickerAnalytics,
                (TickerAnalytics.market == Symbol.market) & (TickerAnalytics.code == Symbol.code),
            )
            .where(*conditions)
            .order_by(
                desc(TickerAnalytics.last_close * func.coalesce(TickerAnalytics.avg_volume_20, 0))
            )
            .limit(request.universe_limit)
        )
    ).all()
    if not rows:
        return []
    symbols = {symbol.code: symbol for symbol, _ in rows}
    analytics = {item.code: item for _, item in rows}
    bars = list(
        await session.scalars(
            select(DailyBar)
            .where(
                DailyBar.market == market,
                DailyBar.code.in_(list(symbols)),
                DailyBar.date >= start_date,
                DailyBar.date <= end_date,
            )
            .order_by(DailyBar.code, DailyBar.date)
        )
    )
    grouped: dict[str, list[StrategyBar]] = {code: [] for code in symbols}
    for bar in bars:
        adjustment = (
            float(bar.adjusted_close) / float(bar.close)
            if bar.adjusted_close is not None and bar.close > 0
            else 1.0
        )
        grouped[bar.code].append(
            StrategyBar(
                date=bar.date,
                open=float(bar.open) * adjustment,
                high=float(bar.high) * adjustment,
                low=float(bar.low) * adjustment,
                close=float(bar.close) * adjustment,
                volume=int(bar.volume),
            )
        )
    return [
        StrategySecurity(
            code=code,
            sector=symbols[code].sector or "Unclassified",
            cap_tier=analytics[code].cap_tier or "unclassified",
            bars=grouped[code],
        )
        for code in symbols
        if grouped[code]
    ]


async def execute_backtest(
    session: AsyncSession,
    *,
    workspace: ResearchWorkspace,
    user_id: int,
    request: BacktestRequest,
) -> ResearchRunOut:
    existing = await _existing_run(
        session, workspace=workspace, idempotency_key=request.idempotency_key
    )
    if existing is not None:
        return await load_research_run(session, workspace=workspace, run_id=existing.id)
    securities = await _backtest_universe(session, market=workspace.market, request=request)
    result = run_backtest(
        market=workspace.market,
        strategy_key=request.strategy_key,
        securities=securities,
        initial_capital=request.initial_capital,
        inactive_security_history_complete=False,
    )
    cutoff = dt.datetime.combine(result.end_date or dt.date.today(), dt.time.max, tzinfo=dt.UTC)
    parameters = request.model_dump(mode="json")
    run = _new_run(
        workspace=workspace,
        user_id=user_id,
        run_kind="hypothesis",
        question=f"Evaluate {request.strategy_key} with point-in-time execution and risk controls.",
        code=None,
        parameters=parameters,
        idempotency_key=request.idempotency_key,
        cutoff=cutoff,
        code_version=ENGINE_VERSION,
    )
    run.evidence_snapshot_hash = _stable_hash(
        {
            security.code: [
                str(security.bars[0].date),
                str(security.bars[-1].date),
                len(security.bars),
            ]
            for security in securities
        }
    )
    await _persist_run_parent(session, run)
    _add_step(
        session,
        run=run,
        ordinal=0,
        kind="experiment_plan",
        output={"request": parameters, "engine_version": ENGINE_VERSION},
    )
    _add_step(
        session,
        run=run,
        ordinal=1,
        kind="observable_universe",
        output={
            "security_count": len(securities),
            "bar_count": sum(len(security.bars) for security in securities),
            "codes": [security.code for security in securities],
            "inactive_security_history_complete": False,
            "point_in_time_universe_complete": False,
        },
    )
    _add_step(
        session,
        run=run,
        ordinal=2,
        kind="portfolio_backtest",
        output=result.model_dump(mode="json"),
        metrics={
            "final_nav": result.final_nav,
            "benchmark_final": result.benchmark_final,
            "fees_paid": result.fees_paid,
            "turnover_pct": result.turnover_pct,
        },
    )
    _add_step(
        session,
        run=run,
        ordinal=3,
        kind="validation_gate",
        output={
            "status": result.validation_status,
            "failed_gates": result.failed_gates,
            "warnings": result.warnings,
        },
    )
    run.parameters = {
        **parameters,
        "result_summary": {
            "strategy": result.strategy.model_dump(mode="json"),
            "validation_status": result.validation_status,
            "failed_gates": result.failed_gates,
            "full_metrics": result.metrics[0].model_dump(mode="json"),
        },
    }
    run.status = "succeeded"
    run.completed_at = dt.datetime.now(dt.UTC)
    await session.flush()
    return await load_research_run(session, workspace=workspace, run_id=run.id)


async def load_research_run(
    session: AsyncSession,
    *,
    workspace: ResearchWorkspace,
    run_id: uuid.UUID,
) -> ResearchRunOut:
    run = await session.scalar(
        select(ResearchRun).where(
            ResearchRun.id == run_id,
            ResearchRun.workspace_id == workspace.id,
            ResearchRun.organization_id == workspace.organization_id,
            ResearchRun.tenant_id == workspace.tenant_id,
            ResearchRun.market == workspace.market,
        )
    )
    if run is None:
        raise LookupError("research run not found")
    steps = list(
        await session.scalars(
            select(ResearchRunStep)
            .where(
                ResearchRunStep.run_id == run.id,
                ResearchRunStep.organization_id == workspace.organization_id,
                ResearchRunStep.tenant_id == workspace.tenant_id,
                ResearchRunStep.market == workspace.market,
            )
            .order_by(ResearchRunStep.ordinal)
        )
    )
    claims = list(
        await session.scalars(
            select(ResearchClaim)
            .where(
                ResearchClaim.run_id == run.id,
                ResearchClaim.organization_id == workspace.organization_id,
                ResearchClaim.tenant_id == workspace.tenant_id,
                ResearchClaim.market == workspace.market,
            )
            .order_by(ResearchClaim.ordinal)
        )
    )
    return ResearchRunOut.from_records(run, steps=steps, claims=claims)


async def list_research_runs(
    session: AsyncSession,
    *,
    workspace: ResearchWorkspace,
    limit: int = 50,
) -> list[ResearchRunOut]:
    runs = list(
        await session.scalars(
            select(ResearchRun)
            .where(
                ResearchRun.workspace_id == workspace.id,
                ResearchRun.organization_id == workspace.organization_id,
                ResearchRun.tenant_id == workspace.tenant_id,
                ResearchRun.market == workspace.market,
            )
            .order_by(ResearchRun.requested_at.desc())
            .limit(limit)
        )
    )
    return [ResearchRunOut.from_records(run, steps=[], claims=[]) for run in runs]
