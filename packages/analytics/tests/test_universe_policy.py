import datetime as dt
import uuid

import pytest

from bulls.analytics.universe_policy import (
    UniverseCohort,
    UniverseDecision,
    UniverseEvidence,
    UniversePolicyInput,
    UniverseReason,
    evaluate_universe,
    evaluate_universe_security,
    universe_input_fingerprint,
)

AS_OF = dt.date(2026, 8, 3)
COMPLETE_US_EVIDENCE = UniverseEvidence(
    listing_point_in_time=True,
    bars_point_in_time=True,
    capitalization_point_in_time=True,
    corporate_actions_complete=True,
    reverse_split_history_complete=True,
)


def _us(code: str = "TEST", **changes) -> UniversePolicyInput:
    values = {
        "market": "US",
        "as_of_date": AS_OF,
        "code": code,
        "security_id": uuid.uuid5(uuid.NAMESPACE_DNS, f"US:{code}"),
        "instrument_type": "common_stock",
        "exchange": "NASDAQ",
        "is_active": True,
        "is_product_eligible": True,
        "latest_bar_date": AS_OF,
        "last_close": 20.0,
        "history_sessions": 300,
        "recent_sessions_observed": 20,
        "recent_sessions_traded": 20,
        "median_traded_value_20_mn": 20.0,
        "market_cap_mn": 5_000.0,
        "recent_reverse_split": False,
        "evidence": COMPLETE_US_EVIDENCE,
    }
    values.update(changes)
    return UniversePolicyInput(**values)


def _dse(code: str = "BSC", **changes) -> UniversePolicyInput:
    values = {
        "market": "DSE",
        "as_of_date": AS_OF,
        "code": code,
        "security_id": uuid.uuid5(uuid.NAMESPACE_DNS, f"DSE:{code}"),
        "instrument_type": "listed_instrument",
        "exchange": "DSE",
        "is_active": True,
        "is_product_eligible": True,
        "category": "A",
        "latest_bar_date": AS_OF,
        "last_close": 124.0,
        "history_sessions": 260,
        "recent_sessions_observed": 20,
        "recent_sessions_traded": 19,
        "median_traded_value_20_mn": 8.0,
        "market_cap_mn": 4_000.0,
        "evidence": UniverseEvidence(
            listing_point_in_time=True,
            bars_point_in_time=True,
            corporate_actions_complete=True,
        ),
    }
    values.update(changes)
    return UniversePolicyInput(**values)


@pytest.mark.parametrize(
    ("item", "cohort"),
    [
        (_us(), UniverseCohort.US_CORE),
        (
            _us(
                "SMALL",
                market_cap_mn=900.0,
                last_close=4.0,
                median_traded_value_20_mn=3.0,
            ),
            UniverseCohort.US_SMALL,
        ),
        (
            _us(
                "MICRO",
                market_cap_mn=80.0,
                last_close=1.2,
                history_sessions=200,
                median_traded_value_20_mn=1.5,
            ),
            UniverseCohort.US_MICRO_PENNY,
        ),
    ],
)
def test_us_cohorts_require_distinct_size_price_and_liquidity_gates(
    item: UniversePolicyInput, cohort: UniverseCohort
) -> None:
    result = evaluate_universe_security(item)

    assert result.decision == UniverseDecision.ELIGIBLE
    assert result.cohort == cohort
    assert result.model_eligible


def test_us_missing_market_cap_is_data_blocked_not_a_negative_stock_opinion() -> None:
    result = evaluate_universe_security(_us(market_cap_mn=None))

    assert result.decision == UniverseDecision.DATA_BLOCKED
    assert UniverseReason.MISSING_MARKET_CAP in result.reasons
    assert result.cohort is None


def test_known_product_exclusion_wins_but_all_data_problems_remain_auditable() -> None:
    result = evaluate_universe_security(
        _us(
            instrument_type="warrant",
            is_product_eligible=False,
            latest_bar_date=None,
            last_close=None,
        )
    )

    assert result.decision == UniverseDecision.INELIGIBLE
    assert UniverseReason.PRODUCT_INELIGIBLE in result.reasons
    assert UniverseReason.INSTRUMENT_TYPE_NOT_ALLOWED in result.reasons
    assert UniverseReason.MISSING_LATEST_BAR in result.reasons
    assert UniverseReason.INVALID_CLOSE in result.reasons


def test_low_liquidity_and_recent_reverse_split_fail_the_micro_cohort() -> None:
    result = evaluate_universe_security(
        _us(
            market_cap_mn=100.0,
            last_close=0.8,
            history_sessions=200,
            median_traded_value_20_mn=0.2,
            recent_reverse_split=True,
        )
    )

    assert result.decision == UniverseDecision.INELIGIBLE
    assert UniverseReason.INSUFFICIENT_LIQUIDITY in result.reasons
    assert UniverseReason.RECENT_REVERSE_SPLIT in result.reasons


def test_current_research_can_be_eligible_while_model_training_fails_closed() -> None:
    result = evaluate_universe_security(
        _us(
            evidence=UniverseEvidence(
                listing_point_in_time=True,
                capitalization_point_in_time=True,
            ),
            recent_reverse_split=None,
        )
    )

    assert result.decision == UniverseDecision.ELIGIBLE
    assert not result.model_eligible
    assert UniverseReason.BARS_EVIDENCE_NOT_POINT_IN_TIME in result.model_blockers
    assert UniverseReason.CORPORATE_ACTION_HISTORY_INCOMPLETE in result.model_blockers
    assert UniverseReason.REVERSE_SPLIT_HISTORY_INCOMPLETE in result.model_blockers


def test_dse_liquid_security_is_separate_from_dse_z_category() -> None:
    eligible = evaluate_universe_security(_dse())
    restricted = evaluate_universe_security(_dse("ZED", category="Z"))

    assert eligible.decision == UniverseDecision.ELIGIBLE
    assert eligible.cohort == UniverseCohort.DSE_LIQUID
    assert eligible.cap_tier == "mid"
    assert restricted.decision == UniverseDecision.INELIGIBLE
    assert UniverseReason.DSE_Z_CATEGORY in restricted.reasons


def test_dse_unadjusted_history_can_be_screened_but_not_used_for_model_promotion() -> None:
    result = evaluate_universe_security(
        _dse(
            evidence=UniverseEvidence(
                listing_point_in_time=True,
                bars_point_in_time=True,
                corporate_actions_complete=False,
            )
        )
    )

    assert result.decision == UniverseDecision.ELIGIBLE
    assert not result.model_eligible
    assert UniverseReason.CORPORATE_ACTION_HISTORY_INCOMPLETE in result.model_blockers


def test_batch_rejects_cross_market_or_cross_date_data_leakage() -> None:
    with pytest.raises(ValueError, match="one market and as-of date"):
        evaluate_universe([_us(), _dse()])

    with pytest.raises(ValueError, match="duplicate security codes"):
        evaluate_universe([_us(), _us()])


def test_input_fingerprint_is_order_independent_and_policy_bound() -> None:
    first = _us("AAA")
    second = _us("BBB")

    assert universe_input_fingerprint([first, second]) == universe_input_fingerprint(
        [second, first]
    )
    assert universe_input_fingerprint([first]) != universe_input_fingerprint([second])
