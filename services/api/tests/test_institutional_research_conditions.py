from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy.dialects import postgresql

from api.institutional_research.conditions import (
    _definition,
    _latest_transition_subquery,
)
from api.institutional_research.schemas import (
    ResearchConditionCalibrationOut,
    ResearchConditionScanOut,
)


def test_condition_definition_is_versioned_and_research_only() -> None:
    definition = _definition("controlled_pullback_context")

    assert definition.version == "1.0.0"
    assert definition.category == "trend context"
    assert "not an intraday pullback strategy" in definition.limitation


def test_unknown_condition_fails_closed() -> None:
    with pytest.raises(ValueError, match="Unknown research condition"):
        _definition("buy_everything")


def test_latest_transition_query_is_explicitly_market_and_version_scoped() -> None:
    query = _latest_transition_subquery("US", "trend_alignment", "1.0.0")
    sql = str(
        query.select().compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "research_condition_transitions.market = 'US'" in sql
    assert "condition_key = 'trend_alignment'" in sql
    assert "condition_version = '1.0.0'" in sql
    assert "methodology_version = 'research-conditions-v1'" in sql
    assert "PARTITION BY research_condition_transitions.code" in sql


def test_scan_contract_labels_reconstructed_calibration_as_incomplete() -> None:
    calibration = ResearchConditionCalibrationOut(
        condition_key="trend_alignment",
        condition_version="1.0.0",
        evidence_mode="reconstructed",
        horizon_sessions=5,
        as_of_date=dt.date(2026, 8, 11),
        history_start_date=dt.date(2025, 6, 1),
        observations=100,
        matured=95,
        pending=5,
        median_return_pct=1.2,
        positive_rate_pct=54.0,
        median_excess_return_pct=0.3,
        benchmark_observations=95,
        average_max_favorable_pct=4.0,
        average_max_adverse_pct=-2.5,
        universe_size=300,
        point_in_time_complete=False,
        warning_text="Survivorship-biased diagnostic.",
    )
    scan = ResearchConditionScanOut(
        tenant_id="bullsofdhaka",
        market="DSE",
        workspace_id=uuid.uuid4(),
        generated_at=dt.datetime(2026, 8, 11, tzinfo=dt.UTC),
        latest_session_date=dt.date(2026, 8, 11),
        methodology_version="research-conditions-v1",
        definition=_definition("trend_alignment"),
        observed_count=0,
        new_count=0,
        returned_count=0,
        items=[],
        calibrations=[calibration],
        warnings=["Not a trade signal."],
    )

    payload = scan.model_dump(by_alias=True)
    assert payload["calibrations"][0]["evidenceMode"] == "reconstructed"
    assert payload["calibrations"][0]["pointInTimeComplete"] is False
    assert "signal" in payload["warnings"][0]
