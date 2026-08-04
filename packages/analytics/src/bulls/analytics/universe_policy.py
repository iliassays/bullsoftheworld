"""Point-in-time research-universe policy for Atlas.

This module deliberately contains no database access.  It turns one dated security observation
into an auditable decision, while keeping three concepts separate:

* product eligibility: whether the instrument belongs in the research surface;
* research eligibility: whether it is seasoned and liquid enough for its cohort; and
* model eligibility: whether the evidence is point-in-time complete enough for training or a
  promotable backtest.

Missing evidence never becomes a negative stock opinion.  It is reported as ``data_blocked`` or
as a model blocker, depending on whether a current research screen can still be computed honestly.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import uuid
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bulls.core.markets import cap_tier

POLICY_KEY = "universe_policy_v1"
POLICY_VERSION = "1.0.0"


class UniverseDecision(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    DATA_BLOCKED = "data_blocked"


class UniverseCohort(StrEnum):
    DSE_LIQUID = "dse_liquid"
    US_CORE = "us_core"
    US_SMALL = "us_small"
    US_MICRO_PENNY = "us_micro_penny"


class UniverseReason(StrEnum):
    MISSING_SECURITY_ID = "missing_security_id"
    LISTING_EVIDENCE_NOT_POINT_IN_TIME = "listing_evidence_not_point_in_time"
    BARS_EVIDENCE_NOT_POINT_IN_TIME = "bars_evidence_not_point_in_time"
    CAPITALIZATION_EVIDENCE_NOT_POINT_IN_TIME = (
        "capitalization_evidence_not_point_in_time"
    )
    CORPORATE_ACTION_HISTORY_INCOMPLETE = "corporate_action_history_incomplete"
    REVERSE_SPLIT_HISTORY_INCOMPLETE = "reverse_split_history_incomplete"
    MISSING_LISTING_STATE = "missing_listing_state"
    INACTIVE_LISTING = "inactive_listing"
    PRODUCT_INELIGIBLE = "product_ineligible"
    HIDDEN_SYMBOL = "hidden_symbol"
    MISSING_INSTRUMENT_TYPE = "missing_instrument_type"
    INSTRUMENT_TYPE_NOT_ALLOWED = "instrument_type_not_allowed"
    ETF_NOT_ALLOWED = "etf_not_allowed"
    TEST_ISSUE_NOT_ALLOWED = "test_issue_not_allowed"
    OTC_NOT_ALLOWED = "otc_not_allowed"
    FINANCIAL_STATUS_RESTRICTED = "financial_status_restricted"
    DSE_Z_CATEGORY = "dse_z_category"
    RECENT_REVERSE_SPLIT = "recent_reverse_split"
    MISSING_LATEST_BAR = "missing_latest_bar"
    STALE_LATEST_BAR = "stale_latest_bar"
    INVALID_CLOSE = "invalid_close"
    MISSING_MARKET_CAP = "missing_market_cap"
    MARKET_CAP_BELOW_FLOOR = "market_cap_below_floor"
    PRICE_BELOW_COHORT_FLOOR = "price_below_cohort_floor"
    INSUFFICIENT_HISTORY = "insufficient_history"
    INSUFFICIENT_RECENT_COVERAGE = "insufficient_recent_coverage"
    INSUFFICIENT_TRADING_FREQUENCY = "insufficient_trading_frequency"
    MISSING_LIQUIDITY = "missing_liquidity"
    INSUFFICIENT_LIQUIDITY = "insufficient_liquidity"


class UniverseEvidence(BaseModel):
    """Evidence-quality flags for the values supplied to the policy."""

    model_config = ConfigDict(frozen=True)

    listing_point_in_time: bool = False
    bars_point_in_time: bool = False
    capitalization_point_in_time: bool = False
    corporate_actions_complete: bool = False
    reverse_split_history_complete: bool = False


class UniversePolicyInput(BaseModel):
    """One security's state as it was knowable for a completed market session."""

    model_config = ConfigDict(frozen=True)

    market: Literal["DSE", "US"]
    as_of_date: dt.date
    code: str = Field(min_length=1, max_length=32)
    security_id: uuid.UUID | None = None
    instrument_type: str | None = None
    exchange: str | None = None
    is_active: bool | None = None
    is_product_eligible: bool | None = None
    is_hidden: bool = False
    is_etf: bool = False
    is_test_issue: bool = False
    financial_status: str | None = None
    category: str | None = None
    latest_bar_date: dt.date | None = None
    last_close: float | None = None
    history_sessions: int = Field(default=0, ge=0)
    recent_sessions_observed: int = Field(default=0, ge=0, le=20)
    recent_sessions_traded: int = Field(default=0, ge=0, le=20)
    median_traded_value_20_mn: float | None = None
    market_cap_mn: float | None = None
    recent_reverse_split: bool | None = None
    evidence: UniverseEvidence = Field(default_factory=UniverseEvidence)

    @model_validator(mode="after")
    def validate_recent_sessions(self) -> UniversePolicyInput:
        if self.recent_sessions_traded > self.recent_sessions_observed:
            raise ValueError("recent_sessions_traded cannot exceed recent_sessions_observed")
        return self


class CohortPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    cohort: UniverseCohort
    minimum_market_cap_mn: float | None = Field(default=None, ge=0)
    maximum_market_cap_mn: float | None = Field(default=None, gt=0)
    minimum_price: float = Field(gt=0)
    minimum_history_sessions: int = Field(gt=0)
    minimum_recent_sessions: int = Field(default=20, ge=1, le=20)
    minimum_traded_sessions: int = Field(default=18, ge=1, le=20)
    minimum_median_traded_value_mn: float = Field(gt=0)


class UniversePolicy(BaseModel):
    """Frozen policy configuration.  Its SHA-256 is persisted beside every snapshot."""

    model_config = ConfigDict(frozen=True)

    key: str = POLICY_KEY
    version: str = POLICY_VERSION
    dse: CohortPolicy = Field(
        default_factory=lambda: CohortPolicy(
            cohort=UniverseCohort.DSE_LIQUID,
            minimum_price=1.0,
            minimum_history_sessions=180,
            minimum_median_traded_value_mn=5.0,
        )
    )
    us_core: CohortPolicy = Field(
        default_factory=lambda: CohortPolicy(
            cohort=UniverseCohort.US_CORE,
            minimum_market_cap_mn=2_000.0,
            minimum_price=5.0,
            minimum_history_sessions=252,
            minimum_median_traded_value_mn=10.0,
        )
    )
    us_small: CohortPolicy = Field(
        default_factory=lambda: CohortPolicy(
            cohort=UniverseCohort.US_SMALL,
            minimum_market_cap_mn=300.0,
            maximum_market_cap_mn=2_000.0,
            minimum_price=2.0,
            minimum_history_sessions=252,
            minimum_median_traded_value_mn=2.0,
        )
    )
    us_micro_penny: CohortPolicy = Field(
        default_factory=lambda: CohortPolicy(
            cohort=UniverseCohort.US_MICRO_PENNY,
            minimum_market_cap_mn=20.0,
            maximum_market_cap_mn=300.0,
            minimum_price=0.5,
            minimum_history_sessions=180,
            minimum_median_traded_value_mn=1.0,
        )
    )

    @property
    def sha256(self) -> str:
        return _sha256(self.model_dump(mode="json"))


class UniversePolicyResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    market: Literal["DSE", "US"]
    as_of_date: dt.date
    code: str
    security_id: uuid.UUID | None
    decision: UniverseDecision
    cohort: UniverseCohort | None
    cap_tier: str | None
    model_eligible: bool
    reasons: tuple[UniverseReason, ...] = ()
    model_blockers: tuple[UniverseReason, ...] = ()
    warnings: tuple[UniverseReason, ...] = ()
    policy_key: str
    policy_version: str
    policy_sha256: str
    input_sha256: str
    metrics: dict[str, float | int | str | None]


def default_universe_policy() -> UniversePolicy:
    return UniversePolicy()


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def universe_input_fingerprint(
    inputs: list[UniversePolicyInput], *, policy: UniversePolicy | None = None
) -> str:
    """Stable fingerprint for an ordered-independent policy input set."""

    selected = policy or default_universe_policy()
    rows = sorted(
        (item.model_dump(mode="json") for item in inputs),
        key=lambda item: (item["market"], item["code"], item["as_of_date"]),
    )
    return _sha256({"policy_sha256": selected.sha256, "inputs": rows})


def _known_number(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def _us_cohort(
    item: UniversePolicyInput, policy: UniversePolicy
) -> tuple[CohortPolicy | None, UniverseReason | None]:
    if not _known_number(item.market_cap_mn):
        return None, UniverseReason.MISSING_MARKET_CAP
    market_cap_mn = float(item.market_cap_mn)
    if market_cap_mn < policy.us_micro_penny.minimum_market_cap_mn:
        return None, UniverseReason.MARKET_CAP_BELOW_FLOOR
    if market_cap_mn < float(policy.us_micro_penny.maximum_market_cap_mn):
        return policy.us_micro_penny, None
    if market_cap_mn < float(policy.us_small.maximum_market_cap_mn):
        return policy.us_small, None
    return policy.us_core, None


def _base_reasons(item: UniversePolicyInput) -> tuple[list[UniverseReason], list[UniverseReason]]:
    exclusions: list[UniverseReason] = []
    blocked: list[UniverseReason] = []
    if item.security_id is None:
        blocked.append(UniverseReason.MISSING_SECURITY_ID)
    if item.is_active is None or item.is_product_eligible is None:
        blocked.append(UniverseReason.MISSING_LISTING_STATE)
    else:
        if not item.is_active:
            exclusions.append(UniverseReason.INACTIVE_LISTING)
        if not item.is_product_eligible:
            exclusions.append(UniverseReason.PRODUCT_INELIGIBLE)
    if item.is_hidden:
        exclusions.append(UniverseReason.HIDDEN_SYMBOL)
    if not item.instrument_type:
        blocked.append(UniverseReason.MISSING_INSTRUMENT_TYPE)
    if item.latest_bar_date is None:
        blocked.append(UniverseReason.MISSING_LATEST_BAR)
    elif item.latest_bar_date != item.as_of_date:
        blocked.append(UniverseReason.STALE_LATEST_BAR)
    if not _known_number(item.last_close) or float(item.last_close) <= 0:
        blocked.append(UniverseReason.INVALID_CLOSE)
    return exclusions, blocked


def _model_blockers(item: UniversePolicyInput) -> list[UniverseReason]:
    blockers: list[UniverseReason] = []
    if not item.evidence.listing_point_in_time:
        blockers.append(UniverseReason.LISTING_EVIDENCE_NOT_POINT_IN_TIME)
    if not item.evidence.bars_point_in_time:
        blockers.append(UniverseReason.BARS_EVIDENCE_NOT_POINT_IN_TIME)
    if item.market == "US" and not item.evidence.capitalization_point_in_time:
        blockers.append(UniverseReason.CAPITALIZATION_EVIDENCE_NOT_POINT_IN_TIME)
    if not item.evidence.corporate_actions_complete:
        blockers.append(UniverseReason.CORPORATE_ACTION_HISTORY_INCOMPLETE)
    if item.market == "US" and not item.evidence.reverse_split_history_complete:
        blockers.append(UniverseReason.REVERSE_SPLIT_HISTORY_INCOMPLETE)
    return blockers


def evaluate_universe_security(
    item: UniversePolicyInput,
    *,
    policy: UniversePolicy | None = None,
) -> UniversePolicyResult:
    """Evaluate one security without reading mutable state or making a trade decision."""

    selected = policy or default_universe_policy()
    exclusions, blocked = _base_reasons(item)
    warnings: list[UniverseReason] = []
    cohort_policy: CohortPolicy | None = None

    instrument_type = (item.instrument_type or "").lower()
    if item.market == "US":
        if instrument_type and instrument_type not in {"common_stock", "adr"}:
            exclusions.append(UniverseReason.INSTRUMENT_TYPE_NOT_ALLOWED)
        if item.is_etf:
            exclusions.append(UniverseReason.ETF_NOT_ALLOWED)
        if item.is_test_issue:
            exclusions.append(UniverseReason.TEST_ISSUE_NOT_ALLOWED)
        if (item.exchange or "").upper().startswith(("OTC", "PINK")):
            exclusions.append(UniverseReason.OTC_NOT_ALLOWED)
        if item.financial_status and item.financial_status.upper() != "N":
            exclusions.append(UniverseReason.FINANCIAL_STATUS_RESTRICTED)
        if item.recent_reverse_split is True:
            exclusions.append(UniverseReason.RECENT_REVERSE_SPLIT)
        cohort_policy, cohort_reason = _us_cohort(item, selected)
        if cohort_reason == UniverseReason.MISSING_MARKET_CAP:
            blocked.append(cohort_reason)
        elif cohort_reason is not None:
            exclusions.append(cohort_reason)
    else:
        if instrument_type and instrument_type not in {"listed_instrument", "common_stock"}:
            exclusions.append(UniverseReason.INSTRUMENT_TYPE_NOT_ALLOWED)
        if (item.category or item.financial_status or "").upper() == "Z":
            exclusions.append(UniverseReason.DSE_Z_CATEGORY)
        cohort_policy = selected.dse

    if cohort_policy is not None and _known_number(item.last_close):
        if float(item.last_close) < cohort_policy.minimum_price:
            exclusions.append(UniverseReason.PRICE_BELOW_COHORT_FLOOR)
        if item.history_sessions < cohort_policy.minimum_history_sessions:
            exclusions.append(UniverseReason.INSUFFICIENT_HISTORY)
        if item.recent_sessions_observed < cohort_policy.minimum_recent_sessions:
            exclusions.append(UniverseReason.INSUFFICIENT_RECENT_COVERAGE)
        if item.recent_sessions_traded < cohort_policy.minimum_traded_sessions:
            exclusions.append(UniverseReason.INSUFFICIENT_TRADING_FREQUENCY)
        if not _known_number(item.median_traded_value_20_mn):
            blocked.append(UniverseReason.MISSING_LIQUIDITY)
        elif (
            float(item.median_traded_value_20_mn)
            < cohort_policy.minimum_median_traded_value_mn
        ):
            exclusions.append(UniverseReason.INSUFFICIENT_LIQUIDITY)

    exclusions = list(dict.fromkeys(exclusions))
    blocked = list(dict.fromkeys(blocked))
    model_blockers = list(dict.fromkeys(_model_blockers(item)))
    if item.market == "US" and item.recent_reverse_split is None:
        warnings.append(UniverseReason.REVERSE_SPLIT_HISTORY_INCOMPLETE)

    if exclusions:
        decision = UniverseDecision.INELIGIBLE
    elif blocked:
        decision = UniverseDecision.DATA_BLOCKED
    else:
        decision = UniverseDecision.ELIGIBLE

    cohort = cohort_policy.cohort if cohort_policy is not None else None
    input_sha256 = _sha256(item.model_dump(mode="json"))
    return UniversePolicyResult(
        market=item.market,
        as_of_date=item.as_of_date,
        code=item.code,
        security_id=item.security_id,
        decision=decision,
        cohort=cohort,
        cap_tier=cap_tier(item.market_cap_mn, item.market),
        model_eligible=decision == UniverseDecision.ELIGIBLE and not model_blockers,
        reasons=tuple(dict.fromkeys([*exclusions, *blocked])),
        model_blockers=tuple(model_blockers),
        warnings=tuple(dict.fromkeys(warnings)),
        policy_key=selected.key,
        policy_version=selected.version,
        policy_sha256=selected.sha256,
        input_sha256=input_sha256,
        metrics={
            "last_close": item.last_close,
            "history_sessions": item.history_sessions,
            "recent_sessions_observed": item.recent_sessions_observed,
            "recent_sessions_traded": item.recent_sessions_traded,
            "median_traded_value_20_mn": item.median_traded_value_20_mn,
            "market_cap_mn": item.market_cap_mn,
            "cohort_minimum_price": cohort_policy.minimum_price if cohort_policy else None,
            "cohort_minimum_history_sessions": (
                cohort_policy.minimum_history_sessions if cohort_policy else None
            ),
            "cohort_minimum_median_traded_value_mn": (
                cohort_policy.minimum_median_traded_value_mn if cohort_policy else None
            ),
        },
    )


def evaluate_universe(
    inputs: list[UniversePolicyInput],
    *,
    policy: UniversePolicy | None = None,
) -> list[UniversePolicyResult]:
    """Evaluate a single market/session input set and reject accidental data mixing."""

    if not inputs:
        return []
    scopes = {(item.market, item.as_of_date) for item in inputs}
    if len(scopes) != 1:
        raise ValueError("A universe evaluation must contain exactly one market and as-of date")
    codes = [item.code for item in inputs]
    if len(codes) != len(set(codes)):
        raise ValueError("A universe evaluation cannot contain duplicate security codes")
    return [evaluate_universe_security(item, policy=policy) for item in inputs]


__all__ = [
    "POLICY_KEY",
    "POLICY_VERSION",
    "CohortPolicy",
    "UniverseCohort",
    "UniverseDecision",
    "UniverseEvidence",
    "UniversePolicy",
    "UniversePolicyInput",
    "UniversePolicyResult",
    "UniverseReason",
    "default_universe_policy",
    "evaluate_universe",
    "evaluate_universe_security",
    "universe_input_fingerprint",
]
