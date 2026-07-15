"""Deterministic, market-calibrated research-attention scoring.

The score ranks where an analyst should spend time. It is deliberately not an expected-return or
trade score. Every output carries its inputs, component coverage, and methodology version so the UI
never presents an unexplained number.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

METHODOLOGY_VERSION: Final = "research-attention-v1"


@dataclass(frozen=True, slots=True)
class ResearchQueuePolicy:
    market: str
    minimum_adv_mn: float
    high_volatility_pct: float
    max_participation_rate: float
    target_exit_days: float
    cap_risk: dict[str, float]


POLICIES: Final[dict[str, ResearchQueuePolicy]] = {
    "DSE": ResearchQueuePolicy(
        market="DSE",
        minimum_adv_mn=2.0,
        high_volatility_pct=55.0,
        max_participation_rate=0.02,
        target_exit_days=3.0,
        cap_risk={"large": 10.0, "mid": 25.0, "small": 50.0, "micro": 75.0},
    ),
    "US": ResearchQueuePolicy(
        market="US",
        minimum_adv_mn=1.0,
        high_volatility_pct=80.0,
        max_participation_rate=0.05,
        target_exit_days=3.0,
        cap_risk={
            "mega": 5.0,
            "large": 10.0,
            "mid": 20.0,
            "small": 40.0,
            "micro": 75.0,
            "penny": 90.0,
        },
    ),
}


@dataclass(frozen=True, slots=True)
class ResearchQueueInputs:
    market: str
    last_close: float
    cap_tier: str | None
    roe: float | None = None
    eps_growth_yoy: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    dividend_yield: float | None = None
    pe_vs_sector: float | None = None
    rsi_14: float | None = None
    mom_3_1: float | None = None
    mom_6_1: float | None = None
    mom_12_1: float | None = None
    above_sma_50: bool | None = None
    above_sma_200: bool | None = None
    volatility: float | None = None
    atr_14: float | None = None
    avg_volume_20: float | None = None


@dataclass(frozen=True, slots=True)
class DimensionScore:
    value: int
    confidence: float
    explanation: str
    inputs: dict[str, float | bool | str | None]


@dataclass(frozen=True, slots=True)
class ResearchQueueScore:
    methodology_version: str
    priority: int
    priority_explanation: str
    quality: DimensionScore
    value: DimensionScore
    momentum: DimensionScore
    risk: DimensionScore
    novelty: DimensionScore
    average_daily_value_mn: float | None
    mandate_capacity_mn: float | None
    target_exit_days: float


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _weighted_score(
    components: list[tuple[str, float | None, float]],
    *,
    explanation: str,
    raw_inputs: dict[str, float | bool | str | None],
) -> DimensionScore:
    available = [(value, weight) for _, value, weight in components if value is not None]
    total_weight = sum(weight for _, _, weight in components)
    used_weight = sum(weight for _, weight in available)
    score = (
        sum(value * weight for value, weight in available) / used_weight if used_weight else 50.0
    )
    return DimensionScore(
        value=round(_clamp(score)),
        confidence=round(used_weight / total_weight, 2) if total_weight else 0.0,
        explanation=explanation,
        inputs=raw_inputs,
    )


def _quality(inputs: ResearchQueueInputs) -> DimensionScore:
    return _weighted_score(
        [
            ("roe", None if inputs.roe is None else _clamp((inputs.roe + 5.0) / 35.0 * 100), 0.4),
            (
                "eps_growth_yoy",
                None
                if inputs.eps_growth_yoy is None
                else _clamp((inputs.eps_growth_yoy + 25.0) / 100.0 * 100),
                0.4,
            ),
            ("positive_earnings", None if inputs.pe_ratio is None else 75.0, 0.2),
        ],
        explanation="Profitability and earnings direction; missing fundamentals lower confidence.",
        raw_inputs={
            "roe_pct": inputs.roe,
            "eps_growth_yoy_pct": inputs.eps_growth_yoy,
            "positive_earnings_observed": inputs.pe_ratio is not None,
        },
    )


def _value(inputs: ResearchQueueInputs) -> DimensionScore:
    return _weighted_score(
        [
            (
                "sector_relative_pe",
                None
                if inputs.pe_vs_sector is None
                else _clamp((1.6 - inputs.pe_vs_sector) / 1.2 * 100),
                0.4,
            ),
            (
                "pe",
                None if inputs.pe_ratio is None else _clamp((40.0 - inputs.pe_ratio) / 35.0 * 100),
                0.25,
            ),
            (
                "pb",
                None if inputs.pb_ratio is None else _clamp((6.0 - inputs.pb_ratio) / 5.5 * 100),
                0.2,
            ),
            (
                "yield",
                None
                if inputs.dividend_yield is None
                else _clamp(inputs.dividend_yield / 8.0 * 100),
                0.15,
            ),
        ],
        explanation="Relative and absolute valuation; this measures cheapness, not a price target.",
        raw_inputs={
            "pe_vs_sector": inputs.pe_vs_sector,
            "pe_ratio": inputs.pe_ratio,
            "pb_ratio": inputs.pb_ratio,
            "dividend_yield_pct": inputs.dividend_yield,
        },
    )


def _momentum(inputs: ResearchQueueInputs) -> DimensionScore:
    def momentum_score(value: float | None) -> float | None:
        return None if value is None else _clamp((value + 30.0) / 60.0 * 100)

    def boolean_score(value: bool | None) -> float | None:
        return None if value is None else (75.0 if value else 25.0)

    rsi_score = None if inputs.rsi_14 is None else _clamp(100.0 - abs(inputs.rsi_14 - 60.0) * 2.5)
    return _weighted_score(
        [
            ("mom_3_1", momentum_score(inputs.mom_3_1), 0.2),
            ("mom_6_1", momentum_score(inputs.mom_6_1), 0.2),
            ("mom_12_1", momentum_score(inputs.mom_12_1), 0.15),
            ("rsi_14", rsi_score, 0.15),
            ("above_sma_50", boolean_score(inputs.above_sma_50), 0.15),
            ("above_sma_200", boolean_score(inputs.above_sma_200), 0.15),
        ],
        explanation="Multi-horizon trend strength with an extension penalty around extreme RSI.",
        raw_inputs={
            "mom_3_1_pct": inputs.mom_3_1,
            "mom_6_1_pct": inputs.mom_6_1,
            "mom_12_1_pct": inputs.mom_12_1,
            "rsi_14": inputs.rsi_14,
            "above_sma_50": inputs.above_sma_50,
            "above_sma_200": inputs.above_sma_200,
        },
    )


def _risk(
    inputs: ResearchQueueInputs,
    policy: ResearchQueuePolicy,
    *,
    evidence_coverage: float,
) -> tuple[DimensionScore, float | None]:
    adv_mn = (
        None
        if inputs.avg_volume_20 is None
        else inputs.last_close * inputs.avg_volume_20 / 1_000_000.0
    )
    liquidity_risk = (
        None
        if adv_mn is None
        else _clamp((policy.minimum_adv_mn - adv_mn) / policy.minimum_adv_mn * 100)
    )
    atr_pct = (
        None
        if inputs.atr_14 is None or inputs.last_close <= 0
        else inputs.atr_14 / inputs.last_close * 100
    )
    cap_risk = policy.cap_risk.get(inputs.cap_tier or "", 65.0)
    return (
        _weighted_score(
            [
                (
                    "volatility",
                    None
                    if inputs.volatility is None
                    else _clamp(inputs.volatility / policy.high_volatility_pct * 100),
                    0.3,
                ),
                ("atr", None if atr_pct is None else _clamp(atr_pct / 8.0 * 100), 0.2),
                ("liquidity", liquidity_risk, 0.25),
                ("capitalization", cap_risk, 0.15),
                ("evidence_gap", _clamp((1.0 - evidence_coverage) * 100), 0.1),
            ],
            explanation="Higher means more research burden from volatility, liquidity, size, or evidence gaps.",
            raw_inputs={
                "volatility_pct": inputs.volatility,
                "atr_pct": atr_pct,
                "average_daily_value_mn": adv_mn,
                "minimum_adv_mn": policy.minimum_adv_mn,
                "cap_tier": inputs.cap_tier,
                "evidence_coverage": round(evidence_coverage, 2),
            },
        ),
        adv_mn,
    )


def _novelty(days_since_evidence: int | None) -> DimensionScore:
    if days_since_evidence is None:
        value = 20.0
    elif days_since_evidence <= 1:
        value = 100.0
    elif days_since_evidence <= 7:
        value = 100.0 - (days_since_evidence - 1) * 8.0
    elif days_since_evidence <= 30:
        value = 52.0 - (days_since_evidence - 7) * 1.5
    else:
        value = 10.0
    return DimensionScore(
        value=round(_clamp(value)),
        confidence=1.0 if days_since_evidence is not None else 0.0,
        explanation="Recency of the newest official evidence; no source is treated as an evidence gap.",
        inputs={"days_since_official_evidence": days_since_evidence},
    )


def score_research_attention(
    inputs: ResearchQueueInputs,
    *,
    evidence_coverage: float,
    days_since_evidence: int | None,
) -> ResearchQueueScore:
    """Return a reproducible research-priority score and its full calculation trace."""

    try:
        policy = POLICIES[inputs.market]
    except KeyError:
        raise ValueError(f"Unsupported research market: {inputs.market}") from None

    quality = _quality(inputs)
    value = _value(inputs)
    momentum = _momentum(inputs)
    risk, adv_mn = _risk(inputs, policy, evidence_coverage=evidence_coverage)
    novelty = _novelty(days_since_evidence)
    priority = round(
        novelty.value * 0.30
        + risk.value * 0.25
        + momentum.value * 0.20
        + quality.value * 0.15
        + value.value * 0.10
    )
    capacity = (
        None if adv_mn is None else adv_mn * policy.max_participation_rate * policy.target_exit_days
    )
    return ResearchQueueScore(
        methodology_version=METHODOLOGY_VERSION,
        priority=priority,
        priority_explanation=(
            "30% evidence novelty + 25% risk burden + 20% momentum + 15% quality + 10% value. "
            "Priority ranks analyst attention, not expected return."
        ),
        quality=quality,
        value=value,
        momentum=momentum,
        risk=risk,
        novelty=novelty,
        average_daily_value_mn=None if adv_mn is None else round(adv_mn, 4),
        mandate_capacity_mn=None if capacity is None else round(capacity, 4),
        target_exit_days=policy.target_exit_days,
    )
