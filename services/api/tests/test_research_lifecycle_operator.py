from __future__ import annotations

import datetime as dt

import pytest

from api.institutional_research.operator import (
    LifecycleOperatorRequest,
    configure_lifecycle,
)
from api.institutional_research.worker import lifecycle_execution_trigger


def test_scheduled_attempts_share_one_session_trigger() -> None:
    first = lifecycle_execution_trigger(
        "scheduled:first-attempt",
        scheduled=True,
        market="DSE",
        latest_bar=dt.date(2026, 7, 15),
        latest_analytics=dt.date(2026, 7, 15),
    )
    retry = lifecycle_execution_trigger(
        "scheduled:retry",
        scheduled=True,
        market="DSE",
        latest_bar=dt.date(2026, 7, 15),
        latest_analytics=dt.date(2026, 7, 15),
    )

    assert first == retry == "session:DSE:2026-07-15"


def test_operator_attempt_retains_unique_trigger() -> None:
    assert (
        lifecycle_execution_trigger(
            "operator:forced-rerun",
            scheduled=False,
            market="DSE",
            latest_bar=dt.date(2026, 7, 15),
            latest_analytics=dt.date(2026, 7, 15),
        )
        == "operator:forced-rerun"
    )


@pytest.mark.asyncio
async def test_operator_requires_explicit_apply_acknowledgement() -> None:
    with pytest.raises(RuntimeError, match="without --apply"):
        await configure_lifecycle(
            LifecycleOperatorRequest(
                tenant="bullsofdhaka",
                handle="analyst",
                strategy_key="dse_reversal_v1",
                initial_capital=10_000_000,
            )
        )


@pytest.mark.asyncio
async def test_operator_refuses_a_strategy_from_another_tenant_market() -> None:
    with pytest.raises(RuntimeError, match="registered for US, not DSE"):
        await configure_lifecycle(
            LifecycleOperatorRequest(
                tenant="bullsofdhaka",
                handle="analyst",
                strategy_key="us_breakout_v1",
                initial_capital=10_000_000,
                apply=True,
            )
        )
