from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class WorkspaceOut(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str
    tenant_id: str
    market: Literal["DSE", "US"]
    name: str
    base_currency: Literal["BDT", "USD"]
    organization_role: str
    workspace_role: str | None


class DimensionOut(ApiModel):
    value: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    explanation: str
    inputs: dict[str, float | bool | str | None]


class FactorsOut(ApiModel):
    quality: int
    value: int
    momentum: int
    risk: int


class FactorDetailsOut(ApiModel):
    quality: DimensionOut
    value: DimensionOut
    momentum: DimensionOut
    risk: DimensionOut
    novelty: DimensionOut


class EvidenceRequirementOut(ApiModel):
    key: str
    label: str
    present: bool
    as_of: dt.date | None


class EvidenceItemOut(ApiModel):
    id: str
    source: str
    title: str
    published_at: dt.date
    purpose: Literal["supporting", "counter", "context"] = "context"
    confidence: Literal["primary", "derived"] = "primary"
    url: str | None = None


class EvidenceOut(ApiModel):
    freshness: Literal["fresh", "aging", "gap"]
    source_count: int
    counter_count: int | None = None
    coverage_pct: int = Field(ge=0, le=100)
    known_at: dt.datetime
    requirements: list[EvidenceRequirementOut]
    items: list[EvidenceItemOut]


class LiquidityOut(ApiModel):
    average_daily_value: str
    capacity: str
    exit_days: float
    basis: str


class ResearchCandidateOut(ApiModel):
    id: str
    market: Literal["DSE", "US"]
    ticker: str
    company: str
    sector: str
    cap_tier: str
    currency: Literal["BDT", "USD"]
    price: float
    daily_change_pct: float | None
    priority: int = Field(ge=0, le=100)
    priority_explanation: str
    methodology_version: str
    status: Literal["new_evidence", "needs_review", "monitoring"]
    owner: str | None = None
    queue_reason: str
    key_change: str
    thesis_summary: str
    invalidation: str
    catalyst: None = None
    factors: FactorsOut
    factor_details: FactorDetailsOut
    evidence: EvidenceOut
    liquidity: LiquidityOut
    flags: list[str]
    scenarios: list[dict] = Field(default_factory=list)
    sparkline: list[float] = Field(default_factory=list)


class ResearchQueueSnapshotOut(ApiModel):
    tenant_id: str
    market: Literal["DSE", "US"]
    workspace_id: uuid.UUID
    generated_at: dt.datetime
    knowledge_cutoff_at: dt.datetime
    universe_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    is_truncated: bool
    candidates: list[ResearchCandidateOut]


class DossierPricePointOut(ApiModel):
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: int
    benchmark_close: float | None = None


class DossierMarketDataOut(ApiModel):
    as_of_date: dt.date
    benchmark_code: str
    market_cap_mn: float | None
    free_float_cap_mn: float | None
    week52_high: float | None
    week52_low: float | None
    nearest_support: float | None
    nearest_resistance: float | None
    average_volume_20: float | None
    relative_volume: float | None
    cmf_20: float | None
    obv_slope: float | None
    rsi_14: float | None
    volatility_pct: float | None


class DossierFundamentalsOut(ApiModel):
    pe_ratio: float | None
    pb_ratio: float | None
    dividend_yield_pct: float | None
    roe_pct: float | None
    eps_growth_yoy_pct: float | None
    pe_vs_sector: float | None


class ReportedOwnershipCategoryOut(ApiModel):
    key: Literal["sponsor_director", "government", "institutional", "foreign", "public"]
    label: str
    value_pct: float
    change_pp: float | None


class ReportedOwnershipOut(ApiModel):
    as_of_date: dt.date
    previous_as_of_date: dt.date | None
    composition_total_pct: float
    categories: list[ReportedOwnershipCategoryOut]
    interpretation: str
    limitations: list[str]


class InstitutionalDisclosureOut(ApiModel):
    report_date: dt.date
    public_by: dt.date
    managers_count: int
    total_value_usd: float
    net_share_change: int | None
    net_change_pct: float | None
    adding_managers: int
    reducing_managers: int
    unchanged_managers: int
    net_breadth_pct: float | None
    source_url: str
    interpretation: str
    limitations: list[str]


class ShortActivityOut(ApiModel):
    as_of_date: dt.date
    short_marked_share_pct: float
    average_20_pct: float | None
    deviation_pp: float | None
    activity_vs_20x: float | None
    baseline_sessions: int
    source_url: str
    interpretation: str
    limitations: list[str]


class CompanyDossierOut(ApiModel):
    tenant_id: str
    market: Literal["DSE", "US"]
    workspace_id: uuid.UUID
    generated_at: dt.datetime
    knowledge_cutoff_at: dt.datetime
    candidate: ResearchCandidateOut
    market_data: DossierMarketDataOut
    fundamentals: DossierFundamentalsOut
    price_history: list[DossierPricePointOut]
    reported_ownership: ReportedOwnershipOut | None = None
    institutional_disclosure: InstitutionalDisclosureOut | None = None
    short_activity: ShortActivityOut | None = None
    data_quality_notes: list[str] = Field(default_factory=list)


class StartResearchRequest(ApiModel):
    idempotency_key: str = Field(min_length=8, max_length=96)


class BacktestRequest(ApiModel):
    idempotency_key: str = Field(min_length=8, max_length=96)
    strategy_key: Literal[
        "dse_reversal_v1",
        "us_breakout_v1",
        "us_activist_13d_v1",
        "us_insider_cluster_v1",
        "us_forced_seller_v1",
        "us_factor_sleeve_v1",
    ]
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    cap_tier: Literal["mega", "large", "mid", "small", "micro", "penny"] | None = None
    codes: list[str] = Field(default_factory=list, max_length=500)
    universe_limit: int = Field(default=25, ge=5, le=500)
    initial_capital: float = Field(default=100_000, gt=0, le=100_000_000)


class AutomationPolicyUpdate(ApiModel):
    enabled: bool = False
    queue_limit: int = Field(default=20, ge=1, le=50)
    research_limit: int = Field(default=5, ge=1, le=20)
    cap_tier: Literal["mega", "large", "mid", "small", "micro", "penny"] | None = None
    strategy_key: Literal["dse_reversal_v1", "us_breakout_v1"]
    universe_limit: int = Field(default=25, ge=5, le=30)
    initial_capital: float = Field(default=100_000, gt=0, le=100_000_000)

    @model_validator(mode="after")
    def research_must_fit_queue(self) -> AutomationPolicyUpdate:
        if self.research_limit > self.queue_limit:
            raise ValueError("research_limit cannot exceed queue_limit")
        return self


class AutomationPolicyOut(ApiModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    tenant_id: str
    market: Literal["DSE", "US"]
    enabled: bool
    queue_limit: int
    research_limit: int
    cap_tier: str | None
    strategy_key: str
    universe_limit: int
    initial_capital: float
    next_run_at: dt.datetime | None
    last_started_at: dt.datetime | None
    last_completed_at: dt.datetime | None
    last_run_status: str | None
    last_error: str | None


class LifecycleDispatchOut(ApiModel):
    accepted: bool
    job_id: str
    scheduled_for: dt.datetime


class ResearchRunStepOut(ApiModel):
    ordinal: int
    kind: str
    status: str
    output: dict[str, Any]
    metrics: dict[str, Any]


class ResearchCitationOut(ApiModel):
    evidence_document_id: uuid.UUID
    evidence_span_id: uuid.UUID
    source_type: str
    source_record_id: str
    title: str
    source_url: str | None
    published_at: dt.datetime | None
    known_at: dt.datetime
    fact_key: str | None
    text: str
    relation: str
    relevance: float


class ResearchClaimOut(ApiModel):
    ordinal: int
    claim_type: str
    statement: str
    verdict: str
    confidence: float
    values: dict[str, Any]
    verification: dict[str, Any]
    citations: list[ResearchCitationOut] = Field(default_factory=list)


class ResearchRunOut(ApiModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    tenant_id: str
    market: Literal["DSE", "US"]
    run_kind: str
    status: str
    question: str
    code: str | None
    parameters: dict[str, Any]
    knowledge_cutoff_at: dt.datetime
    provider: str | None
    model: str | None
    code_version: str
    evidence_snapshot_hash: str | None
    requested_at: dt.datetime
    completed_at: dt.datetime | None
    steps: list[ResearchRunStepOut]
    claims: list[ResearchClaimOut]

    @classmethod
    def from_records(
        cls,
        run,
        *,
        steps: list,
        claims: list,
        citations_by_claim: dict[uuid.UUID, list[dict[str, Any]]] | None = None,
    ) -> ResearchRunOut:
        citations_by_claim = citations_by_claim or {}
        return cls(
            id=run.id,
            workspace_id=run.workspace_id,
            tenant_id=run.tenant_id,
            market=run.market,
            run_kind=run.run_kind,
            status=run.status,
            question=run.question,
            code=run.code,
            parameters=run.parameters,
            knowledge_cutoff_at=run.knowledge_cutoff_at,
            provider=run.provider,
            model=run.model,
            code_version=run.code_version,
            evidence_snapshot_hash=run.evidence_snapshot_hash,
            requested_at=run.requested_at,
            completed_at=run.completed_at,
            steps=[
                ResearchRunStepOut(
                    ordinal=step.ordinal,
                    kind=step.step_kind,
                    status=step.status,
                    output=step.output,
                    metrics=step.metrics,
                )
                for step in steps
            ],
            claims=[
                ResearchClaimOut(
                    ordinal=claim.ordinal,
                    claim_type=claim.claim_type,
                    statement=claim.statement,
                    verdict=claim.verdict,
                    confidence=float(Decimal(claim.confidence)),
                    values=claim.values,
                    verification=claim.verification,
                    citations=[
                        ResearchCitationOut(**citation)
                        for citation in citations_by_claim.get(claim.id, [])
                    ],
                )
                for claim in claims
            ],
        )


class CreateShadowPortfolioRequest(ApiModel):
    source_run_id: uuid.UUID
    name: str = Field(min_length=3, max_length=120)


class ClearLadderFreezeRequest(ApiModel):
    """Written review that releases a drawdown-ladder freeze (Phase 15 L3.4 override log)."""

    # Substantive justification is mandatory: the override log is only useful if it says why.
    reason: str = Field(min_length=20, max_length=2000)


class ResearchShadowSnapshotOut(ApiModel):
    id: uuid.UUID
    as_of_date: dt.date
    session_number: int
    nav: float
    cash: float
    benchmark_nav: float
    peak_nav: float
    gross_exposure_pct: float
    drawdown_pct: float
    cumulative_fees: float
    cumulative_turnover: float
    positions: dict[str, Any]
    target_weights: dict[str, Any]
    trades: list[dict[str, Any]]
    risk_interventions: list[dict[str, Any]]


class ResearchShadowPortfolioOut(ApiModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    tenant_id: str
    market: Literal["DSE", "US"]
    source_run_id: uuid.UUID
    name: str
    strategy_key: str
    status: str
    initial_capital: float
    inception_date: dt.date
    last_evaluated_on: dt.date | None
    configuration: dict[str, Any]
    snapshots: list[ResearchShadowSnapshotOut]


class InvestmentMandateUpdate(ApiModel):
    objective: str = Field(min_length=20, max_length=1000)
    benchmark_key: str = Field(min_length=3, max_length=64, pattern="^[a-z0-9_]+$")
    max_gross_exposure_pct: float = Field(gt=0, le=100)
    min_cash_reserve_pct: float = Field(ge=0, lt=100)
    max_position_weight_pct: float = Field(gt=0, le=100)
    max_sector_weight_pct: float = Field(gt=0, le=100)
    max_adv_participation_pct: float = Field(gt=0, le=100)
    portfolio_drawdown_brake_pct: float = Field(gt=0, le=100)
    stress_loss_limit_pct: float = Field(gt=0, le=100)

    @model_validator(mode="after")
    def retain_cash_inside_total_capital(self) -> InvestmentMandateUpdate:
        if self.max_gross_exposure_pct + self.min_cash_reserve_pct > 100:
            raise ValueError("gross exposure plus minimum cash reserve cannot exceed 100%")
        if self.max_position_weight_pct > self.max_gross_exposure_pct:
            raise ValueError("single-position limit cannot exceed gross-exposure limit")
        if self.max_sector_weight_pct < self.max_position_weight_pct:
            raise ValueError("sector limit cannot be smaller than single-position limit")
        return self


class InvestmentMandateOut(InvestmentMandateUpdate):
    id: uuid.UUID
    workspace_id: uuid.UUID
    tenant_id: str
    market: Literal["DSE", "US"]
    version: int
    status: Literal["active", "superseded"]
    specification_hash: str
    effective_at: dt.datetime
    superseded_at: dt.datetime | None


class StrategyTrialOut(ApiModel):
    id: uuid.UUID
    source_run_id: uuid.UUID
    workspace_id: uuid.UUID
    tenant_id: str
    market: Literal["DSE", "US"]
    strategy_key: str
    strategy_version: str
    status: str
    registration_state: Literal["preregistered", "legacy_reconstructed"]
    trial_sequence: int
    multiple_testing_policy: str
    economic_hypothesis: str
    specification: dict[str, Any]
    specification_hash: str
    outcome: dict[str, Any]
    registered_at: dt.datetime
    completed_at: dt.datetime | None


class DecisionEventOut(ApiModel):
    id: uuid.UUID
    portfolio_id: uuid.UUID
    snapshot_id: uuid.UUID
    correlation_id: uuid.UUID
    sequence: int
    event_key: str
    caused_by_event_key: str | None
    event_type: str
    event_state: str
    code: str | None
    effective_date: dt.date
    payload: dict[str, Any]
    payload_hash: str
    recorded_at: dt.datetime


class DecisionDirectionCapabilityOut(ApiModel):
    direction: Literal["long", "short"]
    status: Literal["active", "blocked"]
    reason: str


class DecisionCandidateOut(ApiModel):
    id: str
    portfolio_id: uuid.UUID
    portfolio_name: str
    strategy_key: str
    strategy_name: str
    direction: Literal["long", "short"]
    horizon: Literal["swing", "position"]
    expected_holding: str
    code: str
    company: str
    cap_tier: str
    state: Literal["ready", "manage", "exit", "blocked", "closed"]
    evidence_mode: Literal["forward", "historical_replay"]
    as_of_date: dt.date
    first_discovered_on: dt.date
    is_new: bool
    discovery_price: float | None
    as_of_price: float | None
    return_since_discovery_pct: float | None
    max_favorable_pct: float | None
    max_adverse_pct: float | None
    sessions_since_discovery: int
    target_weight_pct: float
    position_weight_pct: float
    latest_fill_side: Literal["buy", "sell"] | None = None
    latest_fill_price: float | None = None
    latest_fill_date: dt.date | None = None
    risk_reference_price: float | None = None
    invalidation_price: float | None = None
    planning_objective_price: float | None = None
    planning_reward_risk: float | None = None
    exit_policy: str
    headline: str
    story: str
    risk_notes: list[str] = Field(default_factory=list)


class DecisionBoardOut(ApiModel):
    workspace_id: uuid.UUID
    tenant_id: str
    market: Literal["DSE", "US"]
    generated_at: dt.datetime
    selected_date: dt.date | None
    latest_date: dt.date | None
    available_dates: list[dt.date]
    direction_capabilities: list[DecisionDirectionCapabilityOut]
    candidates: list[DecisionCandidateOut]
    methodology: str


class DecisionPricePointOut(ApiModel):
    date: dt.date
    close: float
    volume: int
    return_since_discovery_pct: float | None


class DecisionCandidatePathOut(ApiModel):
    workspace_id: uuid.UUID
    tenant_id: str
    market: Literal["DSE", "US"]
    candidate: DecisionCandidateOut
    points: list[DecisionPricePointOut]
    events: list[DecisionEventOut]
    price_basis: str


class MissingDatasetOut(ApiModel):
    key: str
    description: str


class StrategyReadinessOut(ApiModel):
    key: str
    name: str
    market: Literal["DSE", "US"]
    direction: Literal["long", "short", "long_short"]
    horizon: Literal["scalp", "swing", "position"]
    implemented_strategy_key: str | None
    status: Literal["backtest_ready", "diagnostic_only", "blocked"]
    economic_hypothesis: str
    rationale: str
    missing_data: list[MissingDatasetOut]


class StrategyReadinessBoardOut(ApiModel):
    market: Literal["DSE", "US"]
    tenant_id: str
    generated_at: dt.datetime
    entries: list[StrategyReadinessOut]
    methodology: str


class SqueezeEntryOut(ApiModel):
    market: Literal["DSE", "US"]
    code: str
    company: str
    cap_tier: str
    family: str
    family_label: str
    state: Literal["watch", "forming", "trigger_ready", "confirmed", "exhausted", "failed"]
    previous_state: str | None
    state_reason: str
    is_new: bool
    first_discovered_on: dt.date
    as_of_date: dt.date
    sessions_since_discovery: int
    discovery_price: float | None
    as_of_price: float | None
    return_since_discovery_pct: float | None
    max_favorable_pct: float | None
    max_adverse_pct: float | None
    setup_price: float | None
    trigger_price: float | None
    invalidation_price: float | None
    risk_per_share: float | None
    planning_objective_price: float | None
    planning_reward_risk: float | None
    expected_holding: str
    liquidity_capacity_note: str
    supporting_evidence: list[str]
    counter_evidence: list[str]
    data_quality: list[str]
    missing_evidence: list[str]
    paper_book_status: str
    methodology_version: str


class SqueezeFamilyOut(ApiModel):
    family: str
    label: str
    status: Literal["available", "data_blocked"]
    blocked_reason: str | None = None
    missing_datasets: list[str] = Field(default_factory=list)
    entries: list[SqueezeEntryOut] = Field(default_factory=list)


class SqueezeMonitorOut(ApiModel):
    market: Literal["DSE", "US"]
    tenant_id: str
    generated_at: dt.datetime
    selected_date: dt.date | None
    latest_date: dt.date | None
    available_dates: list[dt.date]
    families: list[SqueezeFamilyOut]
    methodology: str
    limitations: list[str]


class SqueezeChartPointOut(ApiModel):
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: int
    ema_20: float | None = None
    ema_50: float | None = None
    # Anchored at first discovery, computed from DAILY typical price x volume. Never label
    # this plain "VWAP" in the UI: Atlas has no meaningful intraday history.
    anchored_vwap: float | None = None


class SqueezeStateMarkerOut(ApiModel):
    date: dt.date
    state: str
    previous_state: str | None
    reason: str


class SqueezePathOut(ApiModel):
    market: Literal["DSE", "US"]
    tenant_id: str
    family: str
    family_label: str
    entry: SqueezeEntryOut
    points: list[SqueezeChartPointOut]
    state_history: list[SqueezeStateMarkerOut]
    # Which discovery episode this is for the ticker/family (1 = first ever seen), and the start
    # dates of every prior episode up to this archive date — so "discovered before" is explicit.
    discovery_number: int
    prior_discovery_dates: list[dt.date]
    atr_14: float | None
    atr_14_prior: float | None
    atr_change_pct: float | None
    price_basis: str
    overlay_basis: str


class PortfolioRiskLimitCheckOut(ApiModel):
    key: str
    status: Literal["within_limit", "breached", "unavailable"]
    actual: float | None
    limit: float
    unit: Literal["pct", "days"]
    detail: str


class PortfolioStressScenarioOut(ApiModel):
    key: str
    label: str
    shock_pct: float
    estimated_loss_pct: float
    status: Literal["within_limit", "breached"]
    methodology: str


class PortfolioRiskReportOut(ApiModel):
    gross_exposure_pct: float
    cash_reserve_pct: float
    largest_position_pct: float
    largest_sector_pct: float
    concentration_hhi: float
    effective_positions: float
    weighted_average_correlation: float | None
    maximum_pair_correlation: float | None
    maximum_exit_days: float | None
    limit_checks: list[PortfolioRiskLimitCheckOut]
    stress_scenarios: list[PortfolioStressScenarioOut]
    breached_limits: list[str]
    data_quality_notes: list[str]


class PerformanceAttributionComponentOut(ApiModel):
    key: str
    label: str
    contribution_pct: float | None
    quality: Literal["exact", "proxy", "unavailable"]
    explanation: str


class PerformanceAttributionOut(ApiModel):
    portfolio_return_pct: float
    benchmark_return_pct: float
    excess_return_pct: float
    components: list[PerformanceAttributionComponentOut]
    rejected_actions: int
    methodology_version: str


class PortfolioOperatingAnalyticsOut(ApiModel):
    portfolio_id: uuid.UUID
    as_of_date: dt.date | None
    mandate: InvestmentMandateOut
    mandate_version: int
    mandate_binding: Literal["pinned", "legacy_active_fallback"]
    risk: PortfolioRiskReportOut
    attribution: PerformanceAttributionOut
    recent_events: list[DecisionEventOut]


class InvestmentOperatingViewOut(ApiModel):
    workspace_id: uuid.UUID
    tenant_id: str
    market: Literal["DSE", "US"]
    generated_at: dt.datetime
    mandate: InvestmentMandateOut
    trials: list[StrategyTrialOut]
    portfolios: list[PortfolioOperatingAnalyticsOut]


class CalibrationObservationOut(ApiModel):
    id: uuid.UUID
    run_id: uuid.UUID
    code: str
    signal_status: str
    confidence: float
    reference_date: dt.date
    reference_price: float
    horizon_sessions: int
    status: str
    outcome_date: dt.date | None
    outcome_price: float | None
    return_pct: float | None
    max_adverse_pct: float | None
    max_favorable_pct: float | None

    @classmethod
    def from_record(cls, record) -> CalibrationObservationOut:
        return cls(
            id=record.id,
            run_id=record.run_id,
            code=record.code,
            signal_status=record.signal_status,
            confidence=float(record.confidence),
            reference_date=record.reference_date,
            reference_price=float(record.reference_price),
            horizon_sessions=record.horizon_sessions,
            status=record.status,
            outcome_date=record.outcome_date,
            outcome_price=float(record.outcome_price) if record.outcome_price is not None else None,
            return_pct=float(record.return_pct) if record.return_pct is not None else None,
            max_adverse_pct=(
                float(record.max_adverse_pct) if record.max_adverse_pct is not None else None
            ),
            max_favorable_pct=(
                float(record.max_favorable_pct) if record.max_favorable_pct is not None else None
            ),
        )


class CalibrationBucketOut(ApiModel):
    signal_status: str
    horizon_sessions: int
    observations: int
    average_return_pct: float
    positive_rate_pct: float


class CalibrationOut(ApiModel):
    workspace_id: uuid.UUID
    tenant_id: str
    market: Literal["DSE", "US"]
    pending: int
    matured: int
    buckets: list[CalibrationBucketOut]
    observations: list[CalibrationObservationOut]


class CatalystEventOut(ApiModel):
    model_config = ConfigDict(
        alias_generator=_to_camel, populate_by_name=True, from_attributes=True
    )

    id: uuid.UUID
    code: str
    event_type: str
    title: str
    timing_kind: Literal["confirmed", "window"]
    confirmed_date: dt.date | None = None
    window_start: dt.date | None = None
    window_end: dt.date | None = None
    status: Literal["scheduled", "occurred", "cancelled"]
    confidence: Literal["official_confirmed", "official_derived", "inferred_cadence"]
    source_type: str
    source_ref: str
    source_url: str | None = None
    known_at: dt.datetime
    expected_evidence: str | None = None
    outcome: dict[str, Any] | None = None
    details: dict[str, Any] | None = None


class CatalystCalendarOut(ApiModel):
    tenant_id: str
    market: Literal["DSE", "US"]
    workspace_id: uuid.UUID
    generated_at: dt.datetime
    horizon_days: int
    events: list[CatalystEventOut]
