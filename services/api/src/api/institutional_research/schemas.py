from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    close: float
    volume: int


class DossierMarketDataOut(ApiModel):
    as_of_date: dt.date
    market_cap_mn: float | None
    free_float_cap_mn: float | None
    week52_high: float | None
    week52_low: float | None
    nearest_support: float | None
    nearest_resistance: float | None
    average_volume_20: float | None
    relative_volume: float | None
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
