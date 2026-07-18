from __future__ import annotations

import datetime as dt
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.institutional_research.readiness import load_trend_pullback_data_readiness


class _OneResult:
    def __init__(self, value):
        self.value = value

    def one(self):
        return self.value


@pytest.mark.asyncio
async def test_trend_readiness_stays_blocked_after_one_good_capture_session() -> None:
    observed_at = dt.datetime(2026, 7, 19, 8, 45, tzinfo=dt.UTC)
    latest = SimpleNamespace(
        session_date=dt.date(2026, 7, 19),
        status="complete",
        observed_slot_count=20,
        expected_slot_count=20,
        observed_symbol_count=394,
        expected_symbol_count=396,
        slot_completeness_pct=100,
        symbol_completeness_pct=99.495,
        vwap_coverage_pct=98.5,
        counter_regression_count=0,
        latest_observed_at=observed_at,
        research_eligible=True,
        blockers=[],
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[latest, 7_880, 7_880]),
        execute=AsyncMock(
            side_effect=[_OneResult((1, 1, 1, dt.date(2026, 7, 19), dt.date(2026, 7, 19)))]
        ),
    )
    workspace = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id="bullsofdhaka",
        market="DSE",
    )

    readiness = await load_trend_pullback_data_readiness(
        session,
        workspace=workspace,
        now=dt.datetime(2026, 7, 19, 9, 0, tzinfo=dt.UTC),
    )

    assert readiness.state == "data_blocked"
    assert readiness.complete_sessions == 1
    assert readiness.latest_quality is not None
    assert readiness.latest_quality.research_eligible
    assert any("preregistration floor is 60" in blocker for blocker in readiness.blockers)
    assert any("Inactive and delisted" in blocker for blocker in readiness.blockers)


@pytest.mark.asyncio
async def test_trend_readiness_refuses_us_workspace() -> None:
    with pytest.raises(ValueError, match="unavailable for this market"):
        await load_trend_pullback_data_readiness(
            SimpleNamespace(),
            workspace=SimpleNamespace(market="US"),
        )
