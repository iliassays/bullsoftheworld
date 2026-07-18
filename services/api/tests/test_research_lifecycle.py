from __future__ import annotations

import datetime as dt
import uuid
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from api.institutional_research.lifecycle import (
    expected_lifecycle_session,
    next_lifecycle_run_at,
    target_weight_changes,
    upsert_automation_policy,
)
from api.institutional_research.schemas import AutomationPolicyUpdate, BacktestRequest
from bulls.core.models import ResearchWorkspace


def test_lifecycle_slots_follow_each_markets_post_close_data_window() -> None:
    dse = next_lifecycle_run_at("DSE", now=dt.datetime(2026, 7, 15, 10, tzinfo=dt.UTC))
    us = next_lifecycle_run_at("US", now=dt.datetime(2026, 7, 15, 20, tzinfo=dt.UTC))

    assert dse == dt.datetime(2026, 7, 15, 11, 0, tzinfo=dt.UTC)
    assert us == dt.datetime(2026, 7, 15, 23, 30, tzinfo=dt.UTC)


def test_dse_expected_session_opens_at_first_data_gated_attempt() -> None:
    before = expected_lifecycle_session("DSE", now=dt.datetime(2026, 7, 15, 10, 59, tzinfo=dt.UTC))
    after = expected_lifecycle_session("DSE", now=dt.datetime(2026, 7, 15, 11, 1, tzinfo=dt.UTC))

    assert before == dt.date(2026, 7, 14)
    assert after == dt.date(2026, 7, 15)


def test_expected_session_advances_only_after_the_research_slot() -> None:
    before = expected_lifecycle_session("US", now=dt.datetime(2026, 7, 15, 23, 29, tzinfo=dt.UTC))
    after = expected_lifecycle_session("US", now=dt.datetime(2026, 7, 15, 23, 31, tzinfo=dt.UTC))

    assert before == dt.date(2026, 7, 14)
    assert after == dt.date(2026, 7, 15)


def test_target_weight_changes_distinguish_targets_from_executions() -> None:
    changes = target_weight_changes(
        {"EXIT": 0.10, "REDUCE": 0.20, "INCREASE": 0.05},
        {"ENTRY": 0.15, "REDUCE": 0.10, "INCREASE": 0.12},
    )

    assert {item["code"]: item["action"] for item in changes} == {
        "ENTRY": "entry_target",
        "EXIT": "exit_target",
        "INCREASE": "increase_target",
        "REDUCE": "reduce_target",
    }


def test_automation_policy_rejects_more_research_than_queue_capacity() -> None:
    with pytest.raises(ValidationError, match="research_limit cannot exceed queue_limit"):
        AutomationPolicyUpdate(
            strategy_key="dse_reversal_v1",
            queue_limit=4,
            research_limit=5,
        )


def test_leader_capture_is_researchable_but_not_automation_eligible() -> None:
    request = BacktestRequest(
        idempotency_key="leader-capture-research-1",
        strategy_key="us_leader_capture_v1",
        universe_limit=100,
    )
    assert request.strategy_key == "us_leader_capture_v1"

    with pytest.raises(ValidationError):
        AutomationPolicyUpdate(strategy_key="us_leader_capture_v1")


@pytest.mark.asyncio
async def test_policy_cannot_register_a_strategy_from_the_other_market() -> None:
    workspace = ResearchWorkspace(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        tenant_id="bullsofdhaka",
        market="DSE",
        slug="core-equity",
        name="Core equity",
        base_currency="BDT",
        created_by_user_id=7,
    )

    with pytest.raises(ValueError, match="not registered for DSE"):
        await upsert_automation_policy(
            AsyncMock(),
            workspace=workspace,
            user_id=7,
            payload=AutomationPolicyUpdate(strategy_key="us_breakout_v1"),
        )
