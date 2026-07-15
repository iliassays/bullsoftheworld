from __future__ import annotations

import pytest

from bulls.analytics.research_queue import ResearchQueueInputs, score_research_attention


def _inputs(market: str = "US", **overrides) -> ResearchQueueInputs:
    values = {
        "market": market,
        "last_close": 10.0,
        "cap_tier": "small",
        "roe": 18.0,
        "eps_growth_yoy": 22.0,
        "pe_ratio": 14.0,
        "pb_ratio": 1.8,
        "dividend_yield": 2.0,
        "pe_vs_sector": 0.8,
        "rsi_14": 61.0,
        "mom_3_1": 12.0,
        "mom_6_1": 18.0,
        "mom_12_1": 20.0,
        "above_sma_50": True,
        "above_sma_200": True,
        "volatility": 42.0,
        "atr_14": 0.35,
        "avg_volume_20": 300_000.0,
    }
    values.update(overrides)
    return ResearchQueueInputs(**values)


def test_score_is_reproducible_and_exposes_its_methodology() -> None:
    first = score_research_attention(_inputs(), evidence_coverage=0.8, days_since_evidence=2)
    second = score_research_attention(_inputs(), evidence_coverage=0.8, days_since_evidence=2)

    assert first == second
    assert first.methodology_version == "research-attention-v1"
    assert "expected return" in first.priority_explanation
    assert first.quality.inputs["roe_pct"] == 18.0
    assert 0 <= first.priority <= 100


def test_fresh_evidence_raises_attention_without_changing_investment_factors() -> None:
    fresh = score_research_attention(_inputs(), evidence_coverage=1.0, days_since_evidence=0)
    stale = score_research_attention(_inputs(), evidence_coverage=1.0, days_since_evidence=90)

    assert fresh.priority > stale.priority
    assert fresh.quality == stale.quality
    assert fresh.value == stale.value
    assert fresh.momentum == stale.momentum


def test_market_policy_changes_liquidity_capacity_without_market_conditionals() -> None:
    us = score_research_attention(_inputs("US"), evidence_coverage=1.0, days_since_evidence=2)
    dse = score_research_attention(_inputs("DSE"), evidence_coverage=1.0, days_since_evidence=2)

    assert us.mandate_capacity_mn is not None
    assert dse.mandate_capacity_mn is not None
    assert us.mandate_capacity_mn > dse.mandate_capacity_mn


def test_unknown_market_fails_closed() -> None:
    with pytest.raises(ValueError, match="Unsupported research market"):
        score_research_attention(_inputs("UNKNOWN"), evidence_coverage=1.0, days_since_evidence=1)
