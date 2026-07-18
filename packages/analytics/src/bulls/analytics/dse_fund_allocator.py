"""Deterministic DSE fund-level target aggregation across independent research sleeves."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DseSleeveIntent:
    key: str
    priority: int
    budget_weight: float
    target_weights: tuple[tuple[str, float], ...]
    evidence_state: Literal["diagnostic", "admitted"] = "diagnostic"


@dataclass(frozen=True)
class DseFundPolicy:
    maximum_gross_weight: float = 0.85
    minimum_cash_weight: float = 0.15
    maximum_name_weight: float = 0.12
    maximum_sector_weight: float = 0.30


@dataclass(frozen=True)
class DseAllocationIntervention:
    sleeve: str
    code: str | None
    rule: str
    requested_weight: float
    accepted_weight: float


@dataclass(frozen=True)
class DseFundTarget:
    target_weights: tuple[tuple[str, float], ...]
    sleeve_evidence_states: tuple[tuple[str, str], ...]
    sleeve_contributions: tuple[tuple[str, str, float], ...]
    gross_weight: float
    cash_weight: float
    capital_action: Literal["none"]
    interventions: tuple[DseAllocationIntervention, ...]


def _validated_sleeve(intent: DseSleeveIntent) -> dict[str, float]:
    if not intent.key.strip():
        raise ValueError("DSE fund sleeve key cannot be empty")
    if not math.isfinite(intent.budget_weight) or not 0 <= intent.budget_weight <= 1:
        raise ValueError(f"Sleeve {intent.key} has an invalid budget")
    weights = dict(intent.target_weights)
    if len(weights) != len(intent.target_weights):
        raise ValueError(f"Sleeve {intent.key} contains duplicate security targets")
    if any(
        not code.strip() or not math.isfinite(weight) or weight < 0
        for code, weight in weights.items()
    ):
        raise ValueError(f"Sleeve {intent.key} contains an invalid target")
    return weights


def allocate_dse_fund_targets(
    *,
    sleeves: list[DseSleeveIntent],
    sectors: dict[str, str],
    policy: DseFundPolicy | None = None,
) -> DseFundTarget:
    """Combine sleeve intent while preserving a single portfolio-level risk authority.

    The result is a research target only. It never creates an order, fill, paper book, or capital
    action. Sleeve priority is explicit so constraint ownership cannot depend on dict ordering.
    """

    policy = policy or DseFundPolicy()
    policy_values = (
        policy.maximum_gross_weight,
        policy.minimum_cash_weight,
        policy.maximum_name_weight,
        policy.maximum_sector_weight,
    )
    if any(not math.isfinite(value) or value < 0 or value > 1 for value in policy_values):
        raise ValueError("DSE fund policy weights must be between zero and one")
    if policy.maximum_gross_weight + policy.minimum_cash_weight > 1 + 1e-12:
        raise ValueError("DSE fund gross and minimum cash limits are inconsistent")
    sleeve_keys = [intent.key for intent in sleeves]
    if len(set(sleeve_keys)) != len(sleeve_keys):
        raise ValueError("DSE fund sleeve keys must be unique")
    validated = [(intent, _validated_sleeve(intent)) for intent in sleeves]
    if (
        sum(intent.budget_weight for intent, _weights in validated)
        > policy.maximum_gross_weight + 1e-12
    ):
        raise ValueError("DSE sleeve budgets exceed the fund gross mandate")

    target_weights: dict[str, float] = {}
    sector_weights: dict[str, float] = {}
    contributions: list[tuple[str, str, float]] = []
    interventions: list[DseAllocationIntervention] = []
    gross = 0.0

    for intent, requested in sorted(validated, key=lambda item: (item[0].priority, item[0].key)):
        requested_total = sum(requested.values())
        scale = min(1.0, intent.budget_weight / requested_total) if requested_total > 0 else 1.0
        if scale < 1.0:
            interventions.append(
                DseAllocationIntervention(
                    sleeve=intent.key,
                    code=None,
                    rule="sleeve_budget",
                    requested_weight=requested_total,
                    accepted_weight=intent.budget_weight,
                )
            )
        for code, raw_weight in sorted(requested.items(), key=lambda item: (-item[1], item[0])):
            desired = raw_weight * scale
            sector = sectors.get(code, "Unclassified")
            constraints = (
                (
                    "fund_name_limit",
                    policy.maximum_name_weight - target_weights.get(code, 0.0),
                ),
                (
                    "fund_sector_limit",
                    policy.maximum_sector_weight - sector_weights.get(sector, 0.0),
                ),
                ("fund_gross_limit", policy.maximum_gross_weight - gross),
            )
            accepted = min(desired, *(available for _rule, available in constraints))
            accepted = max(accepted, 0.0)
            if accepted < desired - 1e-12:
                binding_rule = next(
                    rule for rule, available in constraints if available <= accepted + 1e-12
                )
                interventions.append(
                    DseAllocationIntervention(
                        sleeve=intent.key,
                        code=code,
                        rule=binding_rule,
                        requested_weight=desired,
                        accepted_weight=accepted,
                    )
                )
            if accepted <= 0:
                continue
            target_weights[code] = target_weights.get(code, 0.0) + accepted
            sector_weights[sector] = sector_weights.get(sector, 0.0) + accepted
            gross += accepted
            contributions.append((intent.key, code, accepted))

    return DseFundTarget(
        target_weights=tuple(sorted(target_weights.items())),
        sleeve_evidence_states=tuple(
            sorted((intent.key, intent.evidence_state) for intent, _weights in validated)
        ),
        sleeve_contributions=tuple(contributions),
        gross_weight=round(gross, 12),
        cash_weight=round(1 - gross, 12),
        capital_action="none",
        interventions=tuple(interventions),
    )
