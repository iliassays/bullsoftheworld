from __future__ import annotations

import datetime as dt
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from api.institutional_research.investment import record_snapshot_decision_events
from bulls.core.models import ResearchDecisionEvent


@pytest.mark.asyncio
async def test_risk_forced_exit_is_not_recorded_as_a_strategy_signal() -> None:
    session = SimpleNamespace(
        scalars=AsyncMock(side_effect=[[], []]),
        scalar=AsyncMock(return_value=None),
        add=Mock(),
        flush=AsyncMock(),
    )
    portfolio_id = uuid.uuid4()
    source_run_id = uuid.uuid4()
    portfolio = SimpleNamespace(
        id=portfolio_id,
        organization_id=1,
        workspace_id=uuid.uuid4(),
        tenant_id="bullsofdhaka",
        market="DSE",
        strategy_key="dse_reversal_v1",
        source_run_id=source_run_id,
    )
    previous = SimpleNamespace(
        target_weights={"AAA": 0.1},
        positions={"AAA": {"shares": 100, "average_cost": 10}},
    )
    snapshot = SimpleNamespace(
        id=uuid.uuid4(),
        session_number=7,
        as_of_date=dt.date(2026, 7, 17),
        target_weights={},
        positions={"AAA": {"shares": 100, "average_cost": 10}},
        trades=[],
        risk_interventions=[
            {
                "code": "AAA",
                "rule": "position_stop",
                "detail": "Next-open exit required by the deterministic position stop.",
            }
        ],
        nav=9_000,
        benchmark_nav=10_000,
        cash=8_000,
        gross_exposure_pct=10,
        drawdown_pct=10,
        cumulative_fees=5,
    )

    await record_snapshot_decision_events(
        session,
        portfolio=portfolio,
        snapshot=snapshot,
        previous=previous,
    )

    events = [
        call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], ResearchDecisionEvent)
    ]
    assert not any(event.event_type == "signal" for event in events)
    risk = next(event for event in events if event.event_type == "risk")
    target = next(event for event in events if event.event_type == "target")
    assert target.caused_by_event_key == risk.event_key
    assert target.payload["origin"] == "risk_policy"
