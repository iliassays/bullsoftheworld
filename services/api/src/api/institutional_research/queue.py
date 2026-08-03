from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from dataclasses import asdict

from sqlalchemy import Date, String, column, func, or_, select, values
from sqlalchemy.ext.asyncio import AsyncSession

from api.institutional_research.evidence import (
    EVIDENCE_ADAPTERS,
    EvidenceBundle,
    ReportedAccumulationEvidence,
)
from api.institutional_research.schemas import (
    DimensionOut,
    EvidenceItemOut,
    EvidenceOut,
    EvidenceRequirementOut,
    FactorDetailsOut,
    FactorsOut,
    LiquidityOut,
    ResearchCandidateOut,
    ResearchClueOut,
    ResearchQueueSnapshotOut,
)
from api.institutional_research.universe import apply_research_product_scope
from bulls.analytics.reported_accumulation import (
    ReportedAccumulationAssessment,
    ReportedAccumulationInput,
    assess_reported_accumulation,
)
from bulls.analytics.research_queue import (
    ResearchQueueInputs,
    ResearchQueueScore,
    score_research_attention,
)
from bulls.core.markets import format_money_millions, get_market_profile
from bulls.core.models import DailyBar, Symbol, TickerAnalytics
from bulls.core.symbol_lifecycle import PRIVATE_RESEARCH_STATUSES


def _as_utc(value: dt.datetime) -> dt.datetime:
    return value.replace(tzinfo=dt.UTC) if value.tzinfo is None else value.astimezone(dt.UTC)


def _dimension(value) -> DimensionOut:
    return DimensionOut(**asdict(value))


def _score_inputs(row: TickerAnalytics) -> ResearchQueueInputs:
    return ResearchQueueInputs(
        market=row.market,
        last_close=row.last_close,
        cap_tier=row.cap_tier,
        roe=row.roe,
        eps_growth_yoy=row.eps_growth_yoy,
        pe_ratio=row.pe_ratio,
        pb_ratio=row.pb_ratio,
        dividend_yield=row.dividend_yield,
        pe_vs_sector=row.pe_vs_sector,
        rsi_14=row.rsi_14,
        mom_3_1=row.mom_3_1,
        mom_6_1=row.mom_6_1,
        mom_12_1=row.mom_12_1,
        above_sma_50=row.above_sma_50,
        above_sma_200=row.above_sma_200,
        volatility=row.volatility,
        atr_14=row.atr_14,
        avg_volume_20=row.avg_volume_20,
    )


async def _price_paths(
    session: AsyncSession,
    *,
    market: str,
    cutoffs: dict[str, dt.date],
) -> dict[str, list[float]]:
    if not cutoffs:
        return {}
    queue_cutoffs = (
        values(
            column("code", String(16)),
            column("cutoff", Date),
            name="research_queue_cutoffs",
        )
        .data(list(cutoffs.items()))
        .cte()
    )
    ranked = (
        select(
            DailyBar.code.label("code"),
            DailyBar.date.label("date"),
            func.coalesce(DailyBar.adjusted_close, DailyBar.close).label("close"),
            func.row_number()
            .over(partition_by=DailyBar.code, order_by=DailyBar.date.desc())
            .label("rank"),
        )
        .join(queue_cutoffs, queue_cutoffs.c.code == DailyBar.code)
        .where(DailyBar.market == market, DailyBar.date <= queue_cutoffs.c.cutoff)
        .subquery()
    )
    rows = (
        await session.execute(
            select(ranked).where(ranked.c.rank <= 12).order_by(ranked.c.code, ranked.c.date)
        )
    ).mappings()
    paths: dict[str, list[float]] = {code: [] for code in cutoffs}
    for row in rows:
        paths[row["code"]].append(float(row["close"]))
    return paths


def _daily_change(path: list[float]) -> float | None:
    if len(path) < 2 or path[-2] == 0:
        return None
    return round((path[-1] / path[-2] - 1.0) * 100.0, 2)


def _freshness(days_since_evidence: int | None) -> str:
    if days_since_evidence is None or days_since_evidence > 45:
        return "gap"
    return "fresh" if days_since_evidence <= 7 else "aging"


def _status(score: ResearchQueueScore, coverage: float) -> str:
    if score.novelty.value >= 70:
        return "new_evidence"
    if score.risk.value >= 70 or coverage < 0.6:
        return "needs_review"
    return "monitoring"


def _queue_reason(score: ResearchQueueScore, coverage: float) -> str:
    if score.novelty.value >= 70:
        return "A recent official record entered the current review window."
    if coverage < 0.6:
        return "Required evidence is incomplete; close the gaps before forming a thesis."
    if score.risk.value >= 70:
        return "Risk and implementation constraints require analyst review."
    if score.momentum.value >= 70:
        return "Price structure strengthened without being treated as an investment conclusion."
    return "The current factor and evidence profile merits monitoring."


def _flags(row: TickerAnalytics, score: ResearchQueueScore, coverage: float) -> list[str]:
    flags: list[str] = []
    if coverage < 0.6:
        flags.append("Evidence gap")
    if score.average_daily_value_mn is None:
        flags.append("Liquidity unknown")
    elif score.risk.inputs.get("average_daily_value_mn", 0) < score.risk.inputs.get(
        "minimum_adv_mn", 0
    ):
        flags.append("Below liquidity floor")
    if row.cap_tier in {"micro", "penny"}:
        flags.append("Micro-cap risk")
    if row.volatility is not None and row.volatility >= 70:
        flags.append("High volatility")
    return flags


def _dse_reported_accumulation_clue(
    analytics: TickerAnalytics,
    reported: ReportedAccumulationEvidence,
    _: ReportedAccumulationAssessment,
) -> ResearchClueOut:
    change = reported.institutional_change_pp or 0
    return ResearchClueOut(
        key="reported_accumulation_near_low",
        title="Reported accumulation near yearly low",
        summary=(
            f"The completed-session close is {analytics.pct_from_52w_low:.1f}% above its "
            f"52-week low, while the reported institutional ownership category increased "
            f"{change:+.2f} percentage points from the prior disclosure."
        ),
        data_as_of=reported.report_date,
        public_as_of=None,
        limitations=[
            "DSE ownership is a delayed category percentage; it does not identify buyers, trades, prices, or intent.",
            "The source stores the reporting period but not a trustworthy publication timestamp, so this clue is excluded from historical point-in-time strategy claims.",
        ],
    )


def _us_reported_accumulation_clue(
    analytics: TickerAnalytics,
    reported: ReportedAccumulationEvidence,
    assessment: ReportedAccumulationAssessment,
) -> ResearchClueOut:
    adding = reported.adding_managers or 0
    reducing = reported.reducing_managers or 0
    breadth = assessment.net_manager_breadth_pct or 0
    return ResearchClueOut(
        key="reported_accumulation_near_low",
        title="Reported accumulation near yearly low",
        summary=(
            f"The completed-session close is {analytics.pct_from_52w_low:.1f}% above its "
            f"52-week low. In the {reported.report_date} Form 13F period, {adding} managers "
            f"reported new/increased positions versus {reducing} reduced/exited positions "
            f"(net breadth {breadth:+.0f}%)."
        ),
        data_as_of=reported.report_date,
        public_as_of=reported.public_date,
        limitations=[
            "Form 13F is delayed and excludes shorts, trade dates, execution prices, and manager intent.",
            "Manager breadth reduces raw-share denominator distortion but does not prove coordinated or current buying.",
        ],
    )


_REPORTED_ACCUMULATION_CLUE_BUILDERS = {
    "DSE": _dse_reported_accumulation_clue,
    "US": _us_reported_accumulation_clue,
}


def _research_clues(
    analytics: TickerAnalytics,
    evidence: EvidenceBundle,
) -> list[ResearchClueOut]:
    reported = evidence.reported_accumulation
    if reported is None:
        return []
    assessment = assess_reported_accumulation(
        ReportedAccumulationInput(
            market=analytics.market,
            pct_above_52w_low=analytics.pct_from_52w_low,
            evidence_age_days=max(0, (analytics.as_of_date - reported.report_date).days),
            institutional_change_pp=reported.institutional_change_pp,
            adding_managers=reported.adding_managers,
            reducing_managers=reported.reducing_managers,
            net_share_change=reported.net_share_change,
            share_basis_comparable=reported.share_basis_comparable,
        )
    )
    if not assessment.eligible or analytics.pct_from_52w_low is None:
        return []
    return [_REPORTED_ACCUMULATION_CLUE_BUILDERS[analytics.market](analytics, reported, assessment)]


def _candidate(
    *,
    symbol: Symbol,
    analytics: TickerAnalytics,
    evidence: EvidenceBundle,
    path: list[float],
    cutoff: dt.date,
) -> ResearchCandidateOut:
    adapter = EVIDENCE_ADAPTERS[analytics.market]
    requirements = adapter.analytics_requirements(analytics) + evidence.requirements
    present = sum(requirement.present for requirement in requirements)
    coverage = present / len(requirements) if requirements else 0.0
    days_since = (
        None
        if evidence.latest_official_date is None
        else max(0, (cutoff - evidence.latest_official_date).days)
    )
    score = score_research_attention(
        _score_inputs(analytics),
        evidence_coverage=coverage,
        days_since_evidence=days_since,
    )
    profile = get_market_profile(analytics.market)
    average_daily_value = format_money_millions(score.average_daily_value_mn, analytics.market)
    capacity = format_money_millions(score.mandate_capacity_mn, analytics.market)
    latest_change = (
        evidence.items[0].title if evidence.items else "No recent official evidence found."
    )

    return ResearchCandidateOut(
        id=f"{analytics.market}:{analytics.code}",
        market=analytics.market,
        ticker=analytics.code,
        company=symbol.name_en,
        sector=symbol.sector or "Unclassified",
        cap_tier=analytics.cap_tier or "unclassified",
        currency=profile.currency_code,
        price=analytics.last_close,
        daily_change_pct=_daily_change(path),
        priority=score.priority,
        priority_explanation=score.priority_explanation,
        methodology_version=score.methodology_version,
        status=_status(score, coverage),
        queue_reason=_queue_reason(score, coverage),
        key_change=latest_change,
        thesis_summary=(
            "No investment thesis has been generated. This entry only identifies research work "
            "supported by the calculation and evidence ledger below."
        ),
        invalidation=(
            "Not applicable until the autonomous research loop records a versioned thesis and "
            "explicit invalidation rules."
        ),
        factors=FactorsOut(
            quality=score.quality.value,
            value=score.value.value,
            momentum=score.momentum.value,
            risk=score.risk.value,
        ),
        factor_details=FactorDetailsOut(
            quality=_dimension(score.quality),
            value=_dimension(score.value),
            momentum=_dimension(score.momentum),
            risk=_dimension(score.risk),
            novelty=_dimension(score.novelty),
        ),
        evidence=EvidenceOut(
            freshness=_freshness(days_since),
            source_count=evidence.official_count,
            coverage_pct=round(coverage * 100),
            known_at=_as_utc(analytics.computed_at),
            requirements=[EvidenceRequirementOut(**asdict(item)) for item in requirements],
            items=[EvidenceItemOut(**asdict(item)) for item in evidence.items],
        ),
        liquidity=LiquidityOut(
            average_daily_value=average_daily_value,
            capacity=capacity,
            exit_days=score.target_exit_days,
            basis=(
                f"{score.target_exit_days:.0f} sessions at the market policy's bounded "
                "participation rate; capacity is not executable size."
            ),
        ),
        research_clues=_research_clues(analytics, evidence),
        flags=_flags(analytics, score, coverage),
        sparkline=path[-11:],
    )


async def _load_evidence_by_analytics_cutoff(
    session: AsyncSession,
    *,
    adapter,
    rows: list[tuple[Symbol, TickerAnalytics]],
) -> dict[str, EvidenceBundle]:
    """Load each symbol's evidence no later than its own analytics snapshot."""

    codes_by_cutoff: dict[dt.date, list[str]] = defaultdict(list)
    for _, analytics in rows:
        codes_by_cutoff[analytics.as_of_date].append(analytics.code)
    evidence: dict[str, EvidenceBundle] = {}
    for cutoff, codes in sorted(codes_by_cutoff.items()):
        evidence.update(await adapter.load(session, codes, cutoff=cutoff))
    return evidence


async def build_research_queue(
    session: AsyncSession,
    *,
    tenant_id: str,
    market: str,
    workspace_id: uuid.UUID,
    limit: int,
    cap_tier: str | None = None,
    query: str | None = None,
) -> ResearchQueueSnapshotOut:
    """Build the current queue from rows constrained to one authenticated market tenant."""

    base_conditions = (
        Symbol.market == market,
        TickerAnalytics.market == market,
        Symbol.is_active.is_(True),
        Symbol.is_hidden.is_(False),
        Symbol.research_status.in_(PRIVATE_RESEARCH_STATUSES),
    )
    filters = list(base_conditions)
    if cap_tier == "unclassified":
        filters.append(TickerAnalytics.cap_tier.is_(None))
    elif cap_tier:
        filters.append(TickerAnalytics.cap_tier == cap_tier)
    normalized_query = (query or "").strip()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        filters.append(
            or_(
                Symbol.code.ilike(pattern),
                Symbol.name_en.ilike(pattern),
                Symbol.sector.ilike(pattern),
            )
        )

    universe_count_statement = (
        select(func.count())
        .select_from(Symbol)
        .join(
            TickerAnalytics,
            (TickerAnalytics.market == Symbol.market) & (TickerAnalytics.code == Symbol.code),
        )
        .where(*base_conditions)
    )
    universe_count = await session.scalar(
        apply_research_product_scope(universe_count_statement, market=market)
    )
    rows_statement = (
        select(Symbol, TickerAnalytics)
        .join(
            TickerAnalytics,
            (TickerAnalytics.market == Symbol.market) & (TickerAnalytics.code == Symbol.code),
        )
        .where(*filters)
    )
    rows = (
        await session.execute(
            apply_research_product_scope(rows_statement, market=market)
        )
    ).all()
    if not rows:
        now = dt.datetime.now(dt.UTC)
        return ResearchQueueSnapshotOut(
            tenant_id=tenant_id,
            market=market,
            workspace_id=workspace_id,
            generated_at=now,
            knowledge_cutoff_at=now,
            universe_count=int(universe_count or 0),
            eligible_count=0,
            returned_count=0,
            is_truncated=False,
            candidates=[],
        )

    adapter = EVIDENCE_ADAPTERS[market]
    evidence = await _load_evidence_by_analytics_cutoff(
        session,
        adapter=adapter,
        rows=rows,
    )
    candidates = [
        _candidate(
            symbol=symbol,
            analytics=analytics,
            evidence=evidence[analytics.code],
            path=[],
            cutoff=analytics.as_of_date,
        )
        for symbol, analytics in rows
    ]
    candidates.sort(key=lambda candidate: (-candidate.priority, candidate.ticker))
    candidates = candidates[:limit]
    analytics_by_code = {analytics.code: analytics for _, analytics in rows}
    paths = await _price_paths(
        session,
        market=market,
        cutoffs={
            candidate.ticker: analytics_by_code[candidate.ticker].as_of_date
            for candidate in candidates
        },
    )
    candidates = [
        candidate.model_copy(
            update={
                "daily_change_pct": _daily_change(paths.get(candidate.ticker, [])),
                "sparkline": paths.get(candidate.ticker, [])[-11:],
            }
        )
        for candidate in candidates
    ]
    knowledge_cutoff = max(_as_utc(analytics.computed_at) for _, analytics in rows)
    return ResearchQueueSnapshotOut(
        tenant_id=tenant_id,
        market=market,
        workspace_id=workspace_id,
        generated_at=dt.datetime.now(dt.UTC),
        knowledge_cutoff_at=knowledge_cutoff,
        universe_count=int(universe_count or 0),
        eligible_count=len(rows),
        returned_count=len(candidates),
        is_truncated=len(rows) > len(candidates),
        candidates=candidates,
    )
