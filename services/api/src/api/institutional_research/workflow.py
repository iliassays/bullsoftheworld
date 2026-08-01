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
from api.institutional_research.dse_squeeze_backtests import (
    prepare_dse_compression_backtest,
)
from api.institutional_research.institutional_backtests import (
    InstitutionalBacktestPreparation,
    prepare_institutional_backtest,
    strategy_code_constants,
)
from api.institutional_research.investment import (
    complete_strategy_trial,
    family_trial_count,
    get_active_mandate,
    mandate_snapshot,
    register_strategy_trial,
    risk_policy_from_mandate,
)
from api.institutional_research.lineage import (
    build_evidence_source_snapshots,
    persist_run_evidence,
)
from api.institutional_research.schemas import BacktestRequest, ResearchRunOut
from api.institutional_research.universe import apply_research_product_scope
from bulls.analytics.adjustments import adjustment_factor
from bulls.analytics.deflated_sharpe import deflated_sharpe_ratio
from bulls.analytics.dse_compression_breakout import CompressionBreakoutPolicy
from bulls.analytics.dse_selective_compression import (
    SelectiveCompressionPolicy,
    evaluate_selective_compression_admission,
)
from bulls.analytics.research_loop import (
    METHODOLOGY_VERSION,
    AutonomousResearchInput,
    ResearchFact,
    run_autonomous_research,
)
from bulls.analytics.research_strategy import (
    ENGINE_VERSION,
    STRATEGIES,
    BenchmarkPoint,
    BenchmarkSeries,
    EquityPoint,
    StrategyBar,
    StrategySecurity,
    run_backtest,
    run_cost_tiered_backtest,
)
from bulls.core.models import (
    DailyBar,
    EvidenceDocument,
    EvidenceSpan,
    MarketSummary,
    ResearchClaim,
    ResearchClaimCitation,
    ResearchOutcomeObservation,
    ResearchRun,
    ResearchRunStep,
    ResearchWorkspace,
    Symbol,
    TickerAnalytics,
)
from bulls.core.symbol_lifecycle import PRIVATE_RESEARCH_STATUSES


def _utc(value: dt.datetime) -> dt.datetime:
    return value.replace(tzinfo=dt.UTC) if value.tzinfo is None else value.astimezone(dt.UTC)


def _stable_hash(value: Any) -> str:
    def canonicalize(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                (
                    key.isoformat() if isinstance(key, (dt.date, dt.datetime)) else str(key)
                ): canonicalize(nested)
                for key, nested in item.items()
            }
        if isinstance(item, (list, tuple)):
            return [canonicalize(nested) for nested in item]
        return item

    encoded = json.dumps(
        canonicalize(value),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
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
        _fact(
            "market_data_as_of_date",
            dossier.market_data.as_of_date.isoformat(),
            cutoff=cutoff,
            source_kind="market_data",
        ),
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
            "cmf_20",
            dossier.market_data.cmf_20,
            cutoff=cutoff,
            source_kind="market_data",
        ),
        _fact(
            "obv_slope",
            dossier.market_data.obv_slope,
            cutoff=cutoff,
            source_kind="market_data",
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
    analytics_source_id = (
        f"ticker-analytics:{candidate.market}:{candidate.ticker}:"
        f"{dossier.market_data.as_of_date.isoformat()}"
    )
    facts = [
        fact.model_copy(update={"source_id": analytics_source_id})
        if fact.source_kind in {"calculation", "market_data"}
        else fact
        for fact in facts
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
                    "finra_as_of_date",
                    activity.as_of_date.isoformat(),
                    cutoff=cutoff,
                    source_kind="official_evidence",
                    source_id=source_id,
                ),
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
        model="finance-reasoner-v3",
    )
    run.evidence_snapshot_hash = result.evidence_fingerprint
    await _persist_run_parent(session, run)
    evidence_sources = build_evidence_source_snapshots(
        payload,
        evidence_items=dossier.candidate.evidence.items,
    )
    fact_spans = await persist_run_evidence(
        session,
        run=run,
        sources=evidence_sources,
    )
    facts_by_key = {fact.key: fact for fact in payload.facts}
    persisted_claims: list[tuple[Any, ResearchClaim]] = []
    for stage in result.stages:
        _add_step(
            session,
            run=run,
            ordinal=stage.ordinal,
            kind=stage.kind,
            output=stage.model_dump(mode="json"),
        )
    for ordinal, claim in enumerate(result.claims):
        claim_row = ResearchClaim(
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
        session.add(claim_row)
        persisted_claims.append((claim, claim_row))
    await session.flush()
    citation_count = 0
    for claim, claim_row in persisted_claims:
        span_ids = list(dict.fromkeys(fact_spans.get(key) for key in claim.fact_keys))
        if not span_ids or any(span_id is None for span_id in span_ids):
            missing = sorted(key for key in claim.fact_keys if key not in fact_spans)
            raise RuntimeError(
                f"research claim {claim.key} has incomplete evidence lineage: {missing}"
            )
        relevance = Decimal("1") / Decimal(len(span_ids))
        for span_id in span_ids:
            session.add(
                ResearchClaimCitation(
                    claim_id=claim_row.id,
                    evidence_span_id=span_id,
                    organization_id=run.organization_id,
                    tenant_id=run.tenant_id,
                    market=run.market,
                    relation="supports",
                    relevance=relevance,
                )
            )
            citation_count += 1
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
        "lineage": {
            "version": "atlas-evidence-v1",
            "document_count": len(evidence_sources),
            "fact_count": len(fact_spans),
            "claim_count": len(persisted_claims),
            "citation_count": citation_count,
        },
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
        Symbol.research_status.in_(PRIVATE_RESEARCH_STATUSES),
        TickerAnalytics.market == market,
    ]
    if request.codes:
        conditions.append(Symbol.code.in_([code.upper() for code in request.codes]))
    if request.cap_tier:
        conditions.append(TickerAnalytics.cap_tier == request.cap_tier)
    statement = (
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
    rows = (await session.execute(apply_research_product_scope(statement, market=market))).all()
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
        if min(bar.open or 0, bar.high or 0, bar.low or 0, bar.close or 0) <= 0:
            continue
        adjustment = adjustment_factor(float(bar.close), bar.adjusted_close)
        if adjustment is None:
            continue
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


async def _backtest_benchmark(
    session: AsyncSession,
    *,
    market: str,
    start_date: dt.date,
    end_date: dt.date,
) -> BenchmarkSeries | None:
    """Load an independent completed-close benchmark for the exact evaluation window."""

    if market == "US":
        rows = (
            await session.execute(
                select(DailyBar.date, DailyBar.close, DailyBar.adjusted_close)
                .where(
                    DailyBar.market == "US",
                    DailyBar.code == "SPY",
                    DailyBar.date >= start_date,
                    DailyBar.date <= end_date,
                )
                .order_by(DailyBar.date)
            )
        ).all()
        points = [
            BenchmarkPoint(
                date=row.date,
                close=float(row.adjusted_close if row.adjusted_close is not None else row.close),
            )
            for row in rows
            if (row.adjusted_close if row.adjusted_close is not None else row.close) > 0
        ]
        return (
            BenchmarkSeries(key="spy_total_return_proxy", label="SPY adjusted close", points=points)
            if points
            else None
        )

    rows = (
        await session.execute(
            select(MarketSummary.date, MarketSummary.dsex)
            .where(
                MarketSummary.market == "DSE",
                MarketSummary.date >= start_date,
                MarketSummary.date <= end_date,
                MarketSummary.dsex.is_not(None),
            )
            .order_by(MarketSummary.date)
        )
    ).all()
    points = [
        BenchmarkPoint(date=row.date, close=float(row.dsex))
        for row in rows
        if row.dsex is not None and row.dsex > 0
    ]
    return (
        BenchmarkSeries(key="dsex_price_index", label="DSEX close", points=points)
        if points
        else None
    )


# Phase 13 §13.2: an edge that cannot survive 30 bps of one-way cost was never an edge.
COST_SURVIVAL_FLOOR_BPS = 30.0
# Books whose evidence is event-shaped. Their only comparator used to be the 21-session
# placebo, which establishes that a return attaches to event timing but says nothing about
# whether the exposure beat the market.
EVENT_BOOK_STRATEGY_KEYS = frozenset({"us_activist_13d_v1", "us_insider_cluster_v1"})


def cost_survival_gate(edge_dies_at_bps: float | None) -> str | None:
    """Return a failed-gate reason when the edge dies at or below the cost floor.

    ``edge_dies_at_bps`` is ``None`` when no stress tier killed the edge, which is the only
    passing case. Kept as a pure function so the gate is testable without a database — this
    is a promotion-blocking rule and a silent regression here would be invisible.
    """
    if edge_dies_at_bps is None or edge_dies_at_bps > COST_SURVIVAL_FLOOR_BPS:
        return None
    return (
        f"Edge dies at {edge_dies_at_bps:.0f} bps one-way cost — "
        f"below the {COST_SURVIVAL_FLOOR_BPS:.0f} bps survival requirement (phase 13 §13.2)."
    )


def event_market_null_gate(
    *,
    strategy_key: str,
    benchmark_valid: bool,
    initial_capital: float,
    benchmark_final: float,
    final_nav: float,
    stress_30_net_return_pct: float | None,
) -> tuple[dict | None, str | None]:
    """Phase 12 market null for event books: beat the market, not just the placebo.

    The book's *cost-loaded* net return is compared against the *uncosted* benchmark, which
    is deliberately the conservative direction — the strategy pays its costs and the
    benchmark does not. Both the realistic and the 30 bps stressed return must clear it.

    A missing 30 bps stress figure fails the gate rather than skipping it: an unmeasurable
    comparison is not a passed comparison.
    """
    if strategy_key not in EVENT_BOOK_STRATEGY_KEYS or not benchmark_valid:
        return None, None
    if initial_capital <= 0:
        return None, None

    benchmark_return = benchmark_final / initial_capital - 1.0
    realistic_net = final_nav / initial_capital - 1.0
    beats_realistic = realistic_net > benchmark_return
    beats_stressed = (
        stress_30_net_return_pct is not None
        and stress_30_net_return_pct / 100.0 > benchmark_return
    )
    summary = {
        "benchmark_return_pct": round(benchmark_return * 100.0, 3),
        "strategy_beats_realistic": beats_realistic,
        "strategy_beats_stress_30bps": beats_stressed,
    }
    if beats_realistic and beats_stressed:
        return summary, None
    return summary, (
        "Event book did not beat the uncosted market benchmark at realistic and 30 bps "
        "costs (phase 12 market null)."
    )


def _deflated_sharpe_gate(
    equity_curve: list[EquityPoint],
    *,
    num_trials: int,
    threshold: float = 0.95,
) -> tuple[dict | None, str | None]:
    """Overfitting-adjusted promotion gate (Phase 13.3.3 / 13.5), computed over the full curve.

    Returns ``(summary, failed_gate)``: the deflated-Sharpe numbers to surface in the run, and a
    failed-gate message when the edge does not clear the trial-count-adjusted bar. ``num_trials``
    is the strategy family's attempt count, so more prior attempts mechanically raise the bar —
    this replaces the earlier flat "attempt > 1 is diagnostic" rule with a graded statistic.

    Pure function (no DB, no I/O) so the gate logic is unit-testable on its own.
    """
    navs = [point.nav for point in equity_curve]
    returns = [navs[i] / navs[i - 1] - 1.0 for i in range(1, len(navs)) if navs[i - 1] > 0]
    result = deflated_sharpe_ratio(returns, num_trials=num_trials, threshold=threshold)
    if result is None:
        # Phase 13.5: a promotable system must carry a positive deflated statistic. If the return
        # history is too thin to compute one, it cannot be eligible — say so rather than pass by
        # omission (the same run already fails the length gate; this keeps the reason explicit).
        return None, (
            "Deflated Sharpe could not be computed from the available return history; a positive "
            "deflated statistic is required before promotion."
        )
    summary = result.model_dump(mode="json")
    if not result.passes:
        return summary, (
            f"Deflated Sharpe {result.deflated_sharpe:.3f} over {num_trials} trial(s) is below "
            f"the {threshold:.2f} overfitting-adjusted promotion bar."
        )
    return summary, None


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
    strategy = STRATEGIES[request.strategy_key]
    if strategy.market != workspace.market:
        raise ValueError(f"Strategy {strategy.key} is not registered for {workspace.market}")
    mandate = await get_active_mandate(session, workspace=workspace)
    if mandate is None:
        raise ValueError("An active investment mandate is required before testing a strategy")
    latest_market_date = request.end_date or await session.scalar(
        select(func.max(DailyBar.date)).where(DailyBar.market == workspace.market)
    )
    cutoff = dt.datetime.combine(latest_market_date or dt.date.today(), dt.time.max, tzinfo=dt.UTC)
    parameters = request.model_dump(mode="json")
    risk_policy = risk_policy_from_mandate(mandate)
    institutional_strategy = request.strategy_key in {
        "us_activist_13d_v1",
        "us_insider_cluster_v1",
        "us_forced_seller_v1",
        "us_factor_sleeve_v1",
    }
    dse_squeeze_strategy = request.strategy_key in {
        "dse_compression_breakout_20d_v1",
        "dse_selective_compression_v1",
    }
    schedule_strategy = institutional_strategy or dse_squeeze_strategy
    execution_timing = "next_close" if institutional_strategy else "next_open"
    signal_specification = (
        {
            "source_family": "compression_breakout",
            "source_methodology": "squeeze-monitor-v3",
            "portfolio_construction": (
                SelectiveCompressionPolicy()
                if request.strategy_key == "dse_selective_compression_v1"
                else CompressionBreakoutPolicy()
            ).model_dump(mode="json"),
            "liquidity_measure": "trailing 20 completed sessions mean(close x volume)",
            "historical_evidence_role": "diagnostic_only",
            "forward_shadow_evidence": "forward rows on or after book registration only",
        }
        if dse_squeeze_strategy
        else None
    )
    frozen_specification = {
        "request": parameters,
        "strategy": strategy.model_dump(mode="json"),
        "risk_policy": risk_policy.model_dump(mode="json"),
        "mandate": mandate_snapshot(mandate),
        "execution": {
            "signal_cutoff": "completed session close",
            "earliest_fill": f"next observable session {execution_timing.removeprefix('next_')}",
            "long_only": True,
        },
        "validation": {
            "chronological_splits": ["train", "validation", "test"],
            "inactive_history_required_for_promotion": True,
            "point_in_time_inputs_required_for_promotion": True,
        },
        **({"signal_specification": signal_specification} if signal_specification else {}),
        # Code-resident constants that define the event family (activist roster, book
        # policy, cluster parameters). Hashing them means editing a constant creates a
        # NEW specification instead of silently rewriting a frozen trial's history.
        **(
            {"code_constants": code_constants}
            if (code_constants := strategy_code_constants(request.strategy_key)) is not None
            else {}
        ),
    }
    run = _new_run(
        workspace=workspace,
        user_id=user_id,
        run_kind="hypothesis",
        question=(
            f"Evaluate {request.strategy_key} with best-available historical execution and "
            "fail-closed point-in-time validation gates."
        ),
        code=None,
        parameters=parameters,
        idempotency_key=request.idempotency_key,
        cutoff=cutoff,
        code_version=ENGINE_VERSION,
    )
    await _persist_run_parent(session, run)
    trial = await register_strategy_trial(
        session,
        workspace=workspace,
        run=run,
        user_id=user_id,
        strategy=strategy,
        specification=frozen_specification,
    )
    preparation = InstitutionalBacktestPreparation(securities=[], weight_schedule={})
    if institutional_strategy:
        preparation = await prepare_institutional_backtest(
            session,
            strategy_key=request.strategy_key,
            request=request,
        )
        securities = preparation.securities
    elif dse_squeeze_strategy:
        preparation = await prepare_dse_compression_backtest(
            session,
            request=request,
        )
        securities = preparation.securities
    else:
        securities = await _backtest_universe(session, market=workspace.market, request=request)
    evaluation_dates = [bar.date for security in securities for bar in security.bars]
    benchmark_series = (
        await _backtest_benchmark(
            session,
            market=workspace.market,
            start_date=min(evaluation_dates),
            end_date=max(evaluation_dates),
        )
        if evaluation_dates
        else None
    )
    cost_tiered = run_cost_tiered_backtest(
        market=workspace.market,
        strategy_key=request.strategy_key,
        securities=securities,
        initial_capital=request.initial_capital,
        inactive_security_history_complete=preparation.inactive_security_history_complete,
        point_in_time_inputs_complete=preparation.point_in_time_inputs_complete,
        risk_policy=risk_policy,
        weight_schedule=preparation.weight_schedule if schedule_strategy else None,
        execution_timing=execution_timing,
        benchmark_series=benchmark_series,
    )
    # The realistic (measured-cost) run is authoritative for the gate and the record; the stress
    # tiers ride alongside as robustness evidence (Phase 13.2 — where does the edge die?).
    result = cost_tiered.primary
    if institutional_strategy:
        required_regimes = {
            "global_financial_crisis_2007_2009",
            "pandemic_dislocation_2020_2021",
            "rates_inflation_2022_2023",
            "recent_2024_onward",
        }
        if request.strategy_key == "us_factor_sleeve_v1":
            required_regimes.add("factor_drought_2017_2020")
        observed_regimes = {item.key for item in result.robustness_slices}
        missing_regimes = sorted(required_regimes - observed_regimes)
        if missing_regimes:
            result = result.model_copy(
                update={
                    "validation_status": "diagnostic",
                    "failed_gates": list(
                        dict.fromkeys(
                            [
                                *result.failed_gates,
                                "Named-regime evidence is incomplete: "
                                + ", ".join(item.replace("_", " ") for item in missing_regimes)
                                + ".",
                            ]
                        )
                    ),
                }
            )
    if preparation.failed_gates:
        result = result.model_copy(
            update={
                "validation_status": "diagnostic",
                "failed_gates": list(
                    dict.fromkeys([*result.failed_gates, *preparation.failed_gates])
                ),
            }
        )

    comparator_summary: dict[str, dict[str, Any]] = {}
    main_stress_30 = next(
        (
            outcome.net_return_pct
            for outcome in cost_tiered.outcomes
            if not outcome.tier.measured and outcome.tier.one_way_bps == 30.0
        ),
        None,
    )
    cost_survival_failure = cost_survival_gate(cost_tiered.edge_dies_at_bps)
    if cost_survival_failure is not None:
        result = result.model_copy(
            update={
                "validation_status": "diagnostic",
                "failed_gates": [*result.failed_gates, cost_survival_failure],
            }
        )
    market_null_summary, market_null_failure = event_market_null_gate(
        strategy_key=request.strategy_key,
        benchmark_valid=result.benchmark_valid,
        initial_capital=result.initial_capital,
        benchmark_final=result.benchmark_final,
        final_nav=result.final_nav,
        stress_30_net_return_pct=main_stress_30,
    )
    if market_null_summary is not None:
        comparator_summary["uncosted_market_benchmark"] = market_null_summary
    if market_null_failure is not None:
        result = result.model_copy(
            update={
                "validation_status": "diagnostic",
                "failed_gates": [*result.failed_gates, market_null_failure],
            }
        )
    if preparation.comparators:
        main_realistic_return = (
            result.final_nav / result.initial_capital - 1.0 if result.initial_capital > 0 else 0.0
        )
        stress_half_spread = max(30.0 - risk_policy.fee_rate * 10_000.0, 0.0)
        failed_nulls: list[str] = []
        for label, schedule in preparation.comparators.items():
            realistic = run_backtest(
                market=workspace.market,
                strategy_key=request.strategy_key,
                securities=securities,
                initial_capital=request.initial_capital,
                risk_policy=risk_policy,
                weight_schedule=schedule,
                execution_timing=execution_timing,
                use_point_in_time_spread=True,
                benchmark_series=benchmark_series,
            )
            stressed = run_backtest(
                market=workspace.market,
                strategy_key=request.strategy_key,
                securities=securities,
                initial_capital=request.initial_capital,
                risk_policy=risk_policy,
                weight_schedule=schedule,
                execution_timing=execution_timing,
                half_spread_bps=stress_half_spread,
                benchmark_series=benchmark_series,
            )
            realistic_return = (
                realistic.final_nav / realistic.initial_capital - 1.0
                if realistic.initial_capital > 0
                else 0.0
            )
            stressed_return_pct = (
                (stressed.final_nav / stressed.initial_capital - 1.0) * 100.0
                if stressed.initial_capital > 0
                else 0.0
            )
            beats_realistic = main_realistic_return > realistic_return
            beats_stressed = main_stress_30 is not None and main_stress_30 > stressed_return_pct
            comparator_summary[label] = {
                "realistic_return_pct": round(realistic_return * 100.0, 3),
                "stress_30bps_return_pct": round(stressed_return_pct, 3),
                "strategy_beats_realistic": beats_realistic,
                "strategy_beats_stress_30bps": beats_stressed,
            }
            if not beats_realistic or not beats_stressed:
                failed_nulls.append(
                    f"Strategy did not beat the {label.replace('_', ' ')} null at realistic and 30 bps costs."
                )
        if failed_nulls:
            result = result.model_copy(
                update={
                    "validation_status": "diagnostic",
                    "failed_gates": list(dict.fromkeys([*result.failed_gates, *failed_nulls])),
                }
            )
    family_trials = await family_trial_count(
        session, workspace=workspace, strategy_key=request.strategy_key
    )
    deflated_sharpe_summary, overfitting_gate = _deflated_sharpe_gate(
        result.equity_curve, num_trials=max(family_trials, trial.trial_sequence)
    )
    if overfitting_gate is not None:
        result = result.model_copy(
            update={
                "validation_status": "diagnostic",
                "failed_gates": [*result.failed_gates, overfitting_gate],
            }
        )
    selective_admission = None
    if request.strategy_key == "dse_selective_compression_v1":
        first_observation = preparation.diagnostics.get("first_observation_date")
        try:
            observation_start = (
                dt.date.fromisoformat(first_observation)
                if isinstance(first_observation, str)
                else None
            )
        except ValueError:
            observation_start = None
        evaluation_curve = [
            point
            for point in result.equity_curve
            if observation_start is None or point.date >= observation_start
        ]
        evaluation_peak = evaluation_curve[0].nav if evaluation_curve else 0.0
        evaluation_drawdown = 0.0
        for point in evaluation_curve:
            evaluation_peak = max(evaluation_peak, point.nav)
            if evaluation_peak > 0:
                evaluation_drawdown = max(
                    evaluation_drawdown,
                    (evaluation_peak - point.nav) / evaluation_peak * 100,
                )
        selective_deflated_sharpe, _selective_overfitting_gate = _deflated_sharpe_gate(
            evaluation_curve,
            num_trials=trial.trial_sequence,
            threshold=0.80,
        )
        selective_admission = evaluate_selective_compression_admission(
            equity_curve=evaluation_curve,
            maximum_drawdown_pct=evaluation_drawdown,
            accepted_entries=int(preparation.diagnostics.get("accepted_entries") or 0),
            buy_executions=sum(trade.side == "buy" for trade in result.trades),
            benchmark_valid=result.benchmark_valid,
            stress_30bps_return_pct=main_stress_30,
            comparator_summary=comparator_summary,
            deflated_sharpe_summary=selective_deflated_sharpe,
        )
        if not selective_admission.passed:
            result = result.model_copy(
                update={
                    "validation_status": "diagnostic",
                    "failed_gates": list(
                        dict.fromkeys(
                            [
                                *result.failed_gates,
                                "Selective forward-observation admission failed: "
                                + ", ".join(selective_admission.failed_checks)
                                + ".",
                            ]
                        )
                    ),
                }
            )
    run.evidence_snapshot_hash = _stable_hash(
        {
            security.code: _stable_hash(
                [
                    [
                        str(bar.date),
                        bar.open,
                        bar.high,
                        bar.low,
                        bar.close,
                        bar.volume,
                    ]
                    for bar in security.bars
                ]
            )
            for security in securities
        }
        | {
            "weight_schedule": _stable_hash(preparation.weight_schedule),
            "execution_timing": execution_timing,
        }
    )
    _add_step(
        session,
        run=run,
        ordinal=0,
        kind="experiment_plan",
        output={
            "frozen_specification": frozen_specification,
            "specification_hash": trial.specification_hash,
            "registered_at": trial.registered_at.isoformat(),
            "engine_version": ENGINE_VERSION,
        },
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
            "point_in_time_inputs_complete": preparation.point_in_time_inputs_complete,
            "preparation": preparation.diagnostics,
        },
    )
    _add_step(
        session,
        run=run,
        ordinal=2,
        kind="system_readiness",
        output={
            "institutional_system": institutional_strategy,
            "schedule_driven_system": schedule_strategy,
            "execution_timing": execution_timing,
            "failed_gates": preparation.failed_gates,
            "diagnostics": preparation.diagnostics,
        },
    )
    _add_step(
        session,
        run=run,
        ordinal=3,
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
        ordinal=4,
        kind="validation_gate",
        output={
            "status": result.validation_status,
            "failed_gates": result.failed_gates,
            "warnings": result.warnings,
            "deflated_sharpe": deflated_sharpe_summary,
            "forward_observation_admission": (
                selective_admission.model_dump(mode="json")
                if selective_admission is not None
                else None
            ),
            "robustness_slices": [
                item.model_dump(mode="json") for item in result.robustness_slices
            ],
        },
    )
    cost_tier_summary = cost_tiered.model_dump(mode="json", exclude={"primary"})
    _add_step(
        session,
        run=run,
        ordinal=5,
        kind="cost_stress",
        output=cost_tier_summary,
        metrics={"edge_dies_at_bps": cost_tiered.edge_dies_at_bps},
    )
    if comparator_summary:
        _add_step(
            session,
            run=run,
            ordinal=6,
            kind="null_models",
            output=comparator_summary,
            metrics={
                "nulls_tested": len(comparator_summary),
                "nulls_beaten_at_both_costs": sum(
                    item["strategy_beats_realistic"] and item["strategy_beats_stress_30bps"]
                    for item in comparator_summary.values()
                ),
            },
        )
    run.parameters = {
        **parameters,
        "result_summary": {
            "strategy": result.strategy.model_dump(mode="json"),
            "validation_status": result.validation_status,
            "failed_gates": result.failed_gates,
            "full_metrics": result.metrics[0].model_dump(mode="json"),
            "deflated_sharpe": deflated_sharpe_summary,
            "forward_observation_admission": (
                selective_admission.model_dump(mode="json")
                if selective_admission is not None
                else None
            ),
            "robustness_slices": [
                item.model_dump(mode="json") for item in result.robustness_slices
            ],
            "cost_stress": {
                "edge_dies_at_bps": cost_tiered.edge_dies_at_bps,
                "measured_coverage": cost_tiered.measured_coverage,
                "universe_size": cost_tiered.universe_size,
                "tiers": [outcome.model_dump(mode="json") for outcome in cost_tiered.outcomes],
            },
            "null_models": comparator_summary,
            "system_readiness": preparation.diagnostics,
        },
    }
    run.status = "succeeded"
    run.completed_at = dt.datetime.now(dt.UTC)
    await complete_strategy_trial(
        session,
        trial=trial,
        validation_status=result.validation_status,
        outcome=run.parameters["result_summary"],
    )
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
    citations_by_claim: dict[uuid.UUID, list[dict[str, Any]]] = {}
    if claims:
        citation_rows = (
            await session.execute(
                select(ResearchClaimCitation, EvidenceSpan, EvidenceDocument)
                .join(
                    EvidenceSpan,
                    (EvidenceSpan.id == ResearchClaimCitation.evidence_span_id)
                    & (EvidenceSpan.tenant_id == ResearchClaimCitation.tenant_id)
                    & (EvidenceSpan.market == ResearchClaimCitation.market),
                )
                .join(
                    EvidenceDocument,
                    (EvidenceDocument.id == EvidenceSpan.document_id)
                    & (EvidenceDocument.tenant_id == EvidenceSpan.tenant_id)
                    & (EvidenceDocument.market == EvidenceSpan.market),
                )
                .where(
                    ResearchClaimCitation.claim_id.in_([claim.id for claim in claims]),
                    ResearchClaimCitation.organization_id == workspace.organization_id,
                    ResearchClaimCitation.tenant_id == workspace.tenant_id,
                    ResearchClaimCitation.market == workspace.market,
                )
                .order_by(ResearchClaimCitation.claim_id, EvidenceSpan.ordinal)
            )
        ).all()
        for citation, span, document in citation_rows:
            citations_by_claim.setdefault(citation.claim_id, []).append(
                {
                    "evidence_document_id": document.id,
                    "evidence_span_id": span.id,
                    "source_type": document.source_type,
                    "source_record_id": document.source_record_id,
                    "title": document.title,
                    "source_url": document.source_url,
                    "published_at": document.published_at,
                    "known_at": document.known_at,
                    "fact_key": span.locator.get("fact_key"),
                    "text": span.text,
                    "relation": citation.relation,
                    "relevance": float(citation.relevance),
                }
            )
    return ResearchRunOut.from_records(
        run,
        steps=steps,
        claims=claims,
        citations_by_claim=citations_by_claim,
    )


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
