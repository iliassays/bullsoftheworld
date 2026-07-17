"""Provider-free autonomous research loop.

The loop turns an already tenant-scoped evidence/calculation pack into a typed thesis, an explicit
counter-thesis, claim verification, and a bounded research decision. It performs no I/O and makes
no portfolio decision. Company-research verdicts and strategy shadow books remain independent.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from bulls.analytics.financial_reasoning import (
    EvidenceRequest,
    FinancialLens,
    FinancialScenario,
    build_financial_reasoning,
)

METHODOLOGY_VERSION = "atlas-finance-reasoner-v3"


class ResearchFact(BaseModel):
    key: str
    label: str
    value: float | int | str | bool | None
    unit: str | None = None
    as_of: str | None = None
    source_kind: Literal["calculation", "official_evidence", "market_data"]
    source_id: str


class AutonomousResearchInput(BaseModel):
    market: Literal["DSE", "US"]
    code: str
    company: str
    knowledge_cutoff_at: str
    quality: int = Field(ge=0, le=100)
    value: int = Field(ge=0, le=100)
    momentum: int = Field(ge=0, le=100)
    risk: int = Field(ge=0, le=100)
    novelty: int = Field(ge=0, le=100)
    quality_confidence: float = Field(ge=0, le=1)
    value_confidence: float = Field(ge=0, le=1)
    momentum_confidence: float = Field(ge=0, le=1)
    risk_confidence: float = Field(ge=0, le=1)
    evidence_coverage_pct: int = Field(ge=0, le=100)
    official_evidence_count: int = Field(ge=0)
    average_daily_value_mn: float | None = Field(default=None, ge=0)
    capacity_mn: float | None = Field(default=None, ge=0)
    cap_tier: str
    flags: list[str] = Field(default_factory=list)
    facts: list[ResearchFact] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicate_fact_keys(self) -> AutonomousResearchInput:
        keys = [fact.key for fact in self.facts]
        if len(keys) != len(set(keys)):
            raise ValueError("Research facts must have unique keys")
        return self


class ResearchClaimResult(BaseModel):
    key: str
    side: Literal["supporting", "counter"]
    statement: str
    fact_keys: list[str]
    verdict: Literal["supported", "mixed", "unsupported", "unknown"]
    confidence: float = Field(ge=0, le=1)
    verification: str
    rule: str


class ResearchStageResult(BaseModel):
    ordinal: int
    kind: Literal["plan", "collect", "analyst", "skeptic", "verify", "decision"]
    summary: str
    output: dict[str, Any]


class AutonomousResearchResult(BaseModel):
    methodology_version: str
    evidence_fingerprint: str
    status: Literal["qualified", "monitor", "rejected", "abstained"]
    confidence: float = Field(ge=0, le=1)
    evidence_completeness_pct: int = Field(ge=0, le=100)
    thesis_strength: Literal["weak", "mixed", "moderate", "strong"]
    outcome_calibration: Literal["uncalibrated"] = "uncalibrated"
    headline: str
    thesis: str
    counter_thesis: str
    invalidation_rules: list[str]
    missing_evidence: list[str]
    strategy_key: str | None
    lenses: list[FinancialLens]
    scenarios: list[FinancialScenario]
    next_evidence: list[EvidenceRequest]
    claims: list[ResearchClaimResult]
    stages: list[ResearchStageResult]
    limitations: list[str]


def _fingerprint(payload: AutonomousResearchInput) -> str:
    encoded = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _verified_claim(
    payload: AutonomousResearchInput,
    *,
    key: str,
    side: Literal["supporting", "counter"],
    statement: str,
    fact_keys: list[str],
    confidence: float,
    rule: str,
) -> ResearchClaimResult:
    available = {fact.key for fact in payload.facts if fact.value is not None}
    matched = [fact_key for fact_key in fact_keys if fact_key in available]
    if not fact_keys:
        verdict = "unknown"
        verification = "No calculation or evidence key was supplied."
        confidence = 0.0
    elif len(matched) == len(fact_keys):
        verdict = "supported"
        verification = "All referenced facts are present in the bounded evidence/calculation pack."
    elif matched:
        verdict = "mixed"
        verification = "Only part of the referenced evidence is available."
        confidence *= len(matched) / len(fact_keys)
    else:
        verdict = "unsupported"
        verification = (
            "The bounded evidence/calculation pack does not contain the referenced facts."
        )
        confidence = 0.0
    return ResearchClaimResult(
        key=key,
        side=side,
        statement=statement,
        fact_keys=fact_keys,
        verdict=verdict,
        confidence=round(max(0.0, min(1.0, confidence)), 3),
        verification=verification,
        rule=rule,
    )


def run_autonomous_research(payload: AutonomousResearchInput) -> AutonomousResearchResult:
    """Execute the bounded analyst -> skeptic -> verifier -> decision loop."""

    values = {fact.key: fact.value for fact in payload.facts if fact.value is not None}
    reasoning = build_financial_reasoning(
        market=payload.market,
        cap_tier=payload.cap_tier,
        facts=values,
        flags=payload.flags,
        official_evidence_count=payload.official_evidence_count,
    )
    verified = [
        _verified_claim(
            payload,
            key=draft.key,
            side=draft.side,
            statement=draft.statement,
            fact_keys=list(draft.fact_keys),
            confidence=draft.confidence,
            rule=draft.rule,
        )
        for draft in reasoning.claim_drafts
    ]
    supporting = [claim for claim in verified if claim.side == "supporting"]
    counter = [claim for claim in verified if claim.side == "counter"]

    if payload.evidence_coverage_pct < 70:
        counter.append(
            _verified_claim(
                payload,
                key="evidence_gap",
                side="counter",
                statement=(
                    f"Required evidence coverage is incomplete ({payload.evidence_coverage_pct}%)."
                ),
                fact_keys=["evidence_coverage"],
                confidence=1.0,
                rule="evidence_coverage_pct < 70",
            )
        )

    missing_evidence: list[str] = []
    if payload.official_evidence_count == 0:
        missing_evidence.append("No current official evidence record is available.")
    if payload.evidence_coverage_pct < 70:
        missing_evidence.append(
            "One or more market-specific evidence requirements are missing or stale."
        )
    if payload.average_daily_value_mn is None:
        missing_evidence.append(
            "Average daily traded value is unavailable, so executable capacity is unknown."
        )
    if payload.quality_confidence < 0.6 or payload.value_confidence < 0.6:
        missing_evidence.append(
            "Fundamental factor coverage is too thin for a high-confidence conclusion."
        )

    supported_bulls = sum(claim.verdict == "supported" for claim in supporting)
    support_strength = sum(claim.confidence for claim in supporting if claim.verdict == "supported")
    counter_strength = sum(claim.confidence for claim in counter if claim.verdict == "supported")
    hard_reject = payload.risk >= 85 or "Below liquidity floor" in payload.flags
    evidence_gate = payload.evidence_coverage_pct >= 60 and payload.official_evidence_count > 0
    if hard_reject:
        status: Literal["qualified", "monitor", "rejected", "abstained"] = "rejected"
    elif not evidence_gate and supported_bulls == 0:
        status = "abstained"
    elif (
        evidence_gate
        and supported_bulls >= 2
        and support_strength >= 1.5
        and payload.risk < 75
        and counter_strength < support_strength
    ):
        status = "qualified"
    else:
        status = "monitor"

    coverage_confidence = payload.evidence_coverage_pct / 100
    factor_confidence = (
        payload.quality_confidence
        + payload.value_confidence
        + payload.momentum_confidence
        + payload.risk_confidence
    ) / 4
    claim_verification = (
        sum(
            1.0 if claim.verdict == "supported" else 0.5 if claim.verdict == "mixed" else 0.0
            for claim in supporting + counter
        )
        / len(supporting + counter)
        if supporting or counter
        else 0.0
    )
    factual_breadth = min(1.0, len(values) / 18)
    confidence = round(
        max(
            0.0,
            min(
                0.9,
                coverage_confidence * 0.35
                + factor_confidence * 0.25
                + claim_verification * 0.25
                + factual_breadth * 0.15,
            ),
        ),
        3,
    )
    if status == "abstained":
        confidence = min(confidence, 0.4)
    elif payload.official_evidence_count == 0:
        confidence = min(confidence, 0.65)

    net_support = support_strength - counter_strength
    if status in {"rejected", "abstained"} or supported_bulls == 0:
        thesis_strength: Literal["weak", "mixed", "moderate", "strong"] = "weak"
    elif counter_strength >= support_strength * 0.75:
        thesis_strength = "mixed"
    elif supported_bulls >= 3 and net_support >= 1.5 and counter_strength < 1.0:
        thesis_strength = "strong"
    elif supported_bulls >= 2 and net_support >= 0.5:
        thesis_strength = "moderate"
    else:
        thesis_strength = "mixed"

    best_support = max(supporting, key=lambda claim: claim.confidence, default=None)
    strongest_risk = max(counter, key=lambda claim: claim.confidence, default=None)
    thesis = (
        best_support.statement
        if best_support
        else "The current bounded evidence pack does not establish a positive research thesis."
    )
    counter_thesis = (
        strongest_risk.statement
        if strongest_risk
        else "No dominant counter-thesis was verified, but absence of a warning is not evidence of safety."
    )
    headline_by_status = {
        "qualified": "Evidence supports testing a bounded hypothesis",
        "monitor": "Keep under review; the case is not yet decisive",
        "rejected": "Current implementation risk fails the research gate",
        "abstained": "Insufficient evidence to form a defensible view",
    }
    price_support = next(
        (
            claim
            for claim in supporting
            if claim.key == "price_structure_support" and claim.verdict == "supported"
        ),
        None,
    )
    strategy_key = (
        "us_breakout_v1"
        if status == "qualified" and payload.market == "US" and price_support
        else None
    )
    invalidation_rules = list(reasoning.invalidation_rules)
    stages = [
        ResearchStageResult(
            ordinal=0,
            kind="plan",
            summary="Compiled a fixed six-stage finance research plan.",
            output={
                "tasks": [
                    "collect_current_facts",
                    "form_thesis",
                    "attempt_disproof",
                    "verify_claims",
                    "apply_evidence_and_risk_gate",
                ]
            },
        ),
        ResearchStageResult(
            ordinal=1,
            kind="collect",
            summary="Bounded the run to the supplied tenant-safe evidence and calculation pack.",
            output={
                "fact_count": len(payload.facts),
                "official_evidence_count": payload.official_evidence_count,
                "coverage_pct": payload.evidence_coverage_pct,
                "financial_lenses": [lens.model_dump() for lens in reasoning.lenses],
            },
        ),
        ResearchStageResult(
            ordinal=2,
            kind="analyst",
            summary=thesis,
            output={"supporting_claims": [claim.model_dump() for claim in supporting]},
        ),
        ResearchStageResult(
            ordinal=3,
            kind="skeptic",
            summary=counter_thesis,
            output={
                "counter_claims": [claim.model_dump() for claim in counter],
                "missing_evidence": missing_evidence,
                "next_evidence": [request.model_dump() for request in reasoning.evidence_requests],
            },
        ),
        ResearchStageResult(
            ordinal=4,
            kind="verify",
            summary="Verified every generated claim against registered fact keys.",
            output={
                "supported": sum(claim.verdict == "supported" for claim in supporting + counter),
                "mixed": sum(claim.verdict == "mixed" for claim in supporting + counter),
                "unsupported": sum(
                    claim.verdict == "unsupported" for claim in supporting + counter
                ),
            },
        ),
        ResearchStageResult(
            ordinal=5,
            kind="decision",
            summary=headline_by_status[status],
            output={
                "status": status,
                "decision_support_score": confidence,
                "evidence_completeness_pct": payload.evidence_coverage_pct,
                "thesis_strength": thesis_strength,
                "outcome_calibration": "uncalibrated",
                "strategy_key": strategy_key,
                "invalidation_rules": invalidation_rules,
                "scenarios": [scenario.model_dump() for scenario in reasoning.scenarios],
            },
        ),
    ]
    return AutonomousResearchResult(
        methodology_version=METHODOLOGY_VERSION,
        evidence_fingerprint=_fingerprint(payload),
        status=status,
        confidence=confidence,
        evidence_completeness_pct=payload.evidence_coverage_pct,
        thesis_strength=thesis_strength,
        outcome_calibration="uncalibrated",
        headline=headline_by_status[status],
        thesis=thesis,
        counter_thesis=counter_thesis,
        invalidation_rules=invalidation_rules,
        missing_evidence=missing_evidence,
        strategy_key=strategy_key,
        lenses=list(reasoning.lenses),
        scenarios=list(reasoning.scenarios),
        next_evidence=list(reasoning.evidence_requests),
        claims=supporting + counter,
        stages=stages,
        limitations=[
            "This provider-free finance reasoner interprets registered evidence and calculations; it does not predict prices.",
            "Qualification permits hypothesis testing only and is not a trade instruction.",
            "Thesis strength is an evidence rubric, not a return probability or price forecast.",
            "Outcome probability remains uncalibrated until sufficient forward observations mature.",
            "Historical strategy validation is a separate gate with separate data requirements.",
            "The engine does not infer document meaning beyond normalized facts and registered disclosure context.",
        ],
    )
