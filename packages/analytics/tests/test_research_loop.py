import pytest
from pydantic import ValidationError

from bulls.analytics.research_loop import (
    AutonomousResearchInput,
    ResearchFact,
    run_autonomous_research,
)


def _payload(**updates) -> AutonomousResearchInput:
    data = {
        "market": "US",
        "code": "TEST",
        "company": "Test Company",
        "knowledge_cutoff_at": "2026-07-15T20:00:00Z",
        "quality": 72,
        "value": 68,
        "momentum": 66,
        "risk": 42,
        "novelty": 80,
        "quality_confidence": 0.9,
        "value_confidence": 0.8,
        "momentum_confidence": 1.0,
        "risk_confidence": 1.0,
        "evidence_coverage_pct": 85,
        "official_evidence_count": 4,
        "average_daily_value_mn": 5.0,
        "capacity_mn": 0.75,
        "cap_tier": "small",
        "flags": [],
        "facts": [
            ResearchFact(
                key=key,
                label=key,
                value=value,
                source_kind=(
                    "official_evidence"
                    if key.startswith("13f_") or key.startswith("finra_")
                    else "calculation"
                ),
                source_id=f"calc:{key}",
            )
            for key, value in {
                "quality_score": 72,
                "value_score": 68,
                "momentum_score": 66,
                "risk_score": 42,
                "evidence_coverage": 85,
                "cap_tier": "small",
                "last_price": 13.0,
                "latest_official_evidence": "10-Q filed",
                "latest_official_evidence_date": "2026-07-14",
                "roe_pct": 18.0,
                "eps_growth_yoy_pct": 25.0,
                "pe_ratio": 12.0,
                "pb_ratio": 1.8,
                "pe_vs_sector": 0.7,
                "mom_3_1_pct": 18.0,
                "above_sma_50": True,
                "above_sma_200": True,
                "rsi_14": 60.0,
                "relative_volume": 1.3,
                "cmf_20": 0.12,
                "obv_slope": 0.2,
                "average_daily_value_mn": 5.0,
                "volatility_pct": 42.0,
                "nearest_support": 10.5,
                "nearest_resistance": 13.2,
                "13f_report_date": "2026-03-31",
                "13f_manager_count": 12,
                "13f_net_breadth_pct": 35.0,
                "13f_net_change_pct": 8.0,
                "finra_short_marked_share_pct": 44.0,
                "finra_average_20_pct": 41.0,
            }.items()
        ],
    }
    data.update(updates)
    return AutonomousResearchInput(**data)


def test_qualified_research_has_verified_claims_and_strategy() -> None:
    result = run_autonomous_research(_payload())

    assert result.status == "qualified"
    assert result.strategy_key == "us_breakout_v1"
    assert result.evidence_fingerprint
    assert len(result.stages) == 6
    assert all(claim.verdict == "supported" for claim in result.claims)
    assert len(result.lenses) == 6
    assert {scenario.key for scenario in result.scenarios} == {"base", "upside", "downside"}
    assert result.next_evidence[0].priority == "routine"
    assert result.evidence_completeness_pct == 85
    assert result.thesis_strength == "strong"
    assert result.outcome_calibration == "uncalibrated"
    assert result.confidence <= 0.9


def test_missing_evidence_abstains_instead_of_guessing() -> None:
    result = run_autonomous_research(
        _payload(
            quality=40,
            value=40,
            momentum=40,
            evidence_coverage_pct=20,
            official_evidence_count=0,
            facts=[],
        )
    )

    assert result.status == "abstained"
    assert result.strategy_key is None
    assert result.confidence <= 0.55
    assert result.missing_evidence


def test_liquidity_failure_rejects_even_with_supporting_factors() -> None:
    result = run_autonomous_research(_payload(flags=["Below liquidity floor"]))

    assert result.status == "rejected"
    assert result.strategy_key is None


def test_missing_current_official_record_caps_interpretation_confidence() -> None:
    result = run_autonomous_research(_payload(official_evidence_count=0))

    assert result.status == "monitor"
    assert result.confidence <= 0.65


def test_claim_with_incomplete_registered_evidence_is_downgraded() -> None:
    base = _payload()
    facts = [
        *[fact for fact in base.facts if not fact.key.startswith("13f_")],
        ResearchFact(
            key="institutional_ownership_pct",
            label="Institutional ownership",
            value=44.0,
            source_kind="official_evidence",
            source_id="ownership:current",
        ),
        ResearchFact(
            key="institutional_ownership_change_pp",
            label="Institutional ownership change",
            value=1.5,
            source_kind="official_evidence",
            source_id="ownership:current",
        ),
    ]
    result = run_autonomous_research(_payload(market="DSE", facts=facts))
    ownership_claim = next(
        claim for claim in result.claims if claim.key == "reported_institutional_increase"
    )

    assert ownership_claim.verdict == "mixed"
    assert ownership_claim.confidence < 0.8


def test_finra_activity_is_context_not_bearish_positioning() -> None:
    result = run_autonomous_research(_payload())
    positioning = next(lens for lens in result.lenses if lens.key == "regulatory_positioning")
    all_claims = " ".join(claim.statement.lower() for claim in result.claims)

    assert "not short interest or bearish conviction" in positioning.summary.lower()
    assert "short-marked" not in all_claims


def test_sector_discount_with_contracting_earnings_is_flagged_as_possible_value_trap() -> None:
    facts = [
        fact.model_copy(update={"value": -18.0}) if fact.key == "eps_growth_yoy_pct" else fact
        for fact in _payload().facts
    ]
    result = run_autonomous_research(_payload(facts=facts))
    valuation = next(lens for lens in result.lenses if lens.key == "valuation")
    claim_keys = {claim.key for claim in result.claims}

    assert valuation.assessment == "caution"
    assert "value trap" in valuation.summary.lower()
    assert {"relative_valuation_support", "earnings_contraction"} <= claim_keys


def test_extreme_growth_requires_base_and_cash_flow_confirmation() -> None:
    facts = [
        fact.model_copy(update={"value": 134.6}) if fact.key == "eps_growth_yoy_pct" else fact
        for fact in _payload().facts
    ]

    result = run_autonomous_research(_payload(facts=facts))
    claim_keys = {claim.key for claim in result.claims}
    fundamentals = next(lens for lens in result.lenses if lens.key == "fundamentals")

    assert "extreme_growth_requires_confirmation" in claim_keys
    assert fundamentals.assessment == "balanced"
    assert any("operating cash flow" in item.question.lower() for item in result.next_evidence)


def test_skeptic_challenges_weak_participation_distribution_and_crowded_entry() -> None:
    updates = {
        "relative_volume": 0.45,
        "cmf_20": -0.12,
        "obv_slope": -0.04,
        "last_price": 126.4,
        "nearest_resistance": 126.7,
        "rsi_14": 70.8,
    }
    facts = [fact.model_copy(update={"value": updates[fact.key]}) if fact.key in updates else fact for fact in _payload().facts]

    result = run_autonomous_research(_payload(facts=facts))
    claim_keys = {claim.key for claim in result.claims}
    structure = next(lens for lens in result.lenses if lens.key == "market_structure")

    assert {"weak_participation", "distribution_pressure", "crowded_near_resistance"} <= claim_keys
    assert structure.assessment == "caution"
    assert result.thesis_strength in {"mixed", "moderate"}


def test_dse_ownership_never_claims_observed_buying() -> None:
    base = _payload()
    facts = [
        *[fact for fact in base.facts if not fact.key.startswith("13f_")],
        ResearchFact(
            key="institutional_ownership_pct",
            label="Institutional ownership",
            value=44.0,
            source_kind="official_evidence",
            source_id="ownership:2026-06",
        ),
        ResearchFact(
            key="institutional_ownership_change_pp",
            label="Institutional ownership change",
            value=1.5,
            source_kind="official_evidence",
            source_id="ownership:2026-06",
        ),
        ResearchFact(
            key="ownership_as_of_date",
            label="Ownership date",
            value="2026-06-30",
            source_kind="official_evidence",
            source_id="ownership:2026-06",
        ),
    ]
    result = run_autonomous_research(_payload(market="DSE", facts=facts))
    ownership_claim = next(
        claim for claim in result.claims if claim.key == "reported_institutional_increase"
    )
    wording = ownership_claim.statement.lower()

    assert "reported institutional ownership increased" in wording
    assert "does not reveal trade dates" in wording
    assert "buying" not in wording


def test_duplicate_fact_keys_are_rejected_before_reasoning() -> None:
    base = _payload()

    with pytest.raises(ValidationError, match="unique keys"):
        _payload(facts=[*base.facts, base.facts[0]])
