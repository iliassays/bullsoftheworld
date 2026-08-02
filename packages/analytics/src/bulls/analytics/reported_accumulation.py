"""Cross-market assessment of reported accumulation near a 52-week low.

This module evaluates a research clue, not a trading signal. Market-specific disclosure
semantics stay in registered policies: DSE provides category-level ownership percentages,
while US Form 13F data provides delayed manager-position aggregates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AccumulationStrength = Literal["gradual", "meaningful", "broad"]


@dataclass(frozen=True, slots=True)
class ReportedAccumulationPolicy:
    market: Literal["DSE", "US"]
    max_pct_above_52w_low: float
    min_institutional_change_pp: float | None = None
    min_manager_actions: int | None = None
    min_net_manager_breadth_pct: float | None = None


@dataclass(frozen=True, slots=True)
class ReportedAccumulationInput:
    market: Literal["DSE", "US"]
    pct_above_52w_low: float | None
    institutional_change_pp: float | None = None
    adding_managers: int | None = None
    reducing_managers: int | None = None
    net_share_change: int | None = None


@dataclass(frozen=True, slots=True)
class ReportedAccumulationAssessment:
    eligible: bool
    strength: AccumulationStrength | None
    net_manager_breadth_pct: float | None
    reason: str


REPORTED_ACCUMULATION_POLICIES: dict[str, ReportedAccumulationPolicy] = {
    "DSE": ReportedAccumulationPolicy(
        market="DSE",
        max_pct_above_52w_low=15.0,
        min_institutional_change_pp=0.10,
    ),
    "US": ReportedAccumulationPolicy(
        market="US",
        max_pct_above_52w_low=15.0,
        min_manager_actions=5,
        min_net_manager_breadth_pct=10.0,
    ),
}


def _near_low(value: float | None, policy: ReportedAccumulationPolicy) -> bool:
    return value is not None and 0 <= value <= policy.max_pct_above_52w_low


def _dse_assessment(
    observation: ReportedAccumulationInput,
    policy: ReportedAccumulationPolicy,
) -> ReportedAccumulationAssessment:
    change = observation.institutional_change_pp
    minimum = policy.min_institutional_change_pp or 0
    if not _near_low(observation.pct_above_52w_low, policy):
        return ReportedAccumulationAssessment(False, None, None, "outside_yearly_low_zone")
    if change is None or change < minimum:
        return ReportedAccumulationAssessment(False, None, None, "no_reported_stake_increase")
    strength: AccumulationStrength = (
        "broad" if change >= 1.0 else "meaningful" if change >= 0.3 else "gradual"
    )
    return ReportedAccumulationAssessment(True, strength, None, "reported_stake_increase")


def _us_assessment(
    observation: ReportedAccumulationInput,
    policy: ReportedAccumulationPolicy,
) -> ReportedAccumulationAssessment:
    if not _near_low(observation.pct_above_52w_low, policy):
        return ReportedAccumulationAssessment(False, None, None, "outside_yearly_low_zone")
    adding = observation.adding_managers or 0
    reducing = observation.reducing_managers or 0
    actions = adding + reducing
    if actions < (policy.min_manager_actions or 0):
        return ReportedAccumulationAssessment(False, None, None, "insufficient_manager_breadth")
    breadth = (adding - reducing) / actions * 100
    if breadth < (policy.min_net_manager_breadth_pct or 0):
        return ReportedAccumulationAssessment(False, None, breadth, "manager_breadth_not_positive")
    if observation.net_share_change is None or observation.net_share_change <= 0:
        return ReportedAccumulationAssessment(False, None, breadth, "net_reported_shares_not_higher")
    strength: AccumulationStrength = (
        "broad" if breadth >= 30 and adding >= 5 else "meaningful"
    )
    return ReportedAccumulationAssessment(True, strength, breadth, "positive_manager_breadth")


_ASSESSORS = {
    "DSE": _dse_assessment,
    "US": _us_assessment,
}


def assess_reported_accumulation(
    observation: ReportedAccumulationInput,
) -> ReportedAccumulationAssessment:
    """Return whether delayed ownership evidence forms the registered research clue."""

    try:
        policy = REPORTED_ACCUMULATION_POLICIES[observation.market]
        assessor = _ASSESSORS[observation.market]
    except KeyError:
        return ReportedAccumulationAssessment(False, None, None, "unsupported_market")
    return assessor(observation, policy)
