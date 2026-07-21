"""Tests for clearing a drawdown-ladder freeze on a shadow book (Phase 15 L2/L3.4)."""

from __future__ import annotations

import datetime as dt
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.institutional_research.portfolio import clear_shadow_ladder_freeze
from bulls.core.models import ResearchShadowPortfolio, ResearchShadowSnapshot, ResearchWorkspace

_ORG = uuid.uuid4()
_WORKSPACE_ID = uuid.uuid4()
_PORTFOLIO_ID = uuid.uuid4()
_GOOD_REASON = "Reviewed the drawdown in writing; thesis intact and exposure re-armed deliberately."


def _workspace() -> ResearchWorkspace:
    return ResearchWorkspace(
        id=_WORKSPACE_ID, organization_id=_ORG, tenant_id="bullsofwallst", market="US"
    )


def _portfolio(*, frozen: bool) -> ResearchShadowPortfolio:
    return ResearchShadowPortfolio(
        id=_PORTFOLIO_ID,
        workspace_id=_WORKSPACE_ID,
        organization_id=_ORG,
        tenant_id="bullsofwallst",
        market="US",
        source_run_id=uuid.uuid4(),
        name="Frozen book",
        strategy_key="us_breakout_v1",
        status="active",
        initial_capital=100_000,
        inception_date=dt.date(2026, 1, 2),
        last_evaluated_on=dt.date(2026, 7, 20),
        configuration={"ladder_frozen": frozen},
    )


def _snapshot() -> ResearchShadowSnapshot:
    return ResearchShadowSnapshot(
        id=uuid.uuid4(),
        portfolio_id=_PORTFOLIO_ID,
        organization_id=_ORG,
        tenant_id="bullsofwallst",
        market="US",
        as_of_date=dt.date(2026, 7, 20),
        session_number=42,
        nav=80_000,
        cash=80_000,
        benchmark_nav=100_000,
        peak_nav=100_000,
        gross_exposure_pct=0,
        drawdown_pct=20,
        cumulative_fees=0,
        cumulative_turnover=0,
        positions={},
        target_weights={},
        trades=[],
        risk_interventions=[],
    )


async def test_blank_reason_is_refused_before_any_lookup() -> None:
    session = AsyncMock()
    with pytest.raises(ValueError, match="written review reason"):
        await clear_shadow_ladder_freeze(
            session,
            workspace=_workspace(),
            portfolio_id=_PORTFOLIO_ID,
            user_id=1,
            reason="   ",
        )
    session.scalar.assert_not_awaited()


async def test_missing_portfolio_raises_lookup_error() -> None:
    session = AsyncMock()
    session.scalar.return_value = None
    with pytest.raises(LookupError):
        await clear_shadow_ladder_freeze(
            session,
            workspace=_workspace(),
            portfolio_id=_PORTFOLIO_ID,
            user_id=1,
            reason=_GOOD_REASON,
        )


async def test_clearing_an_unfrozen_book_is_refused() -> None:
    # Nothing to clear: say so rather than silently recording a meaningless override.
    session = AsyncMock()
    session.scalar.return_value = _portfolio(frozen=False)
    with pytest.raises(ValueError, match="not frozen"):
        await clear_shadow_ladder_freeze(
            session,
            workspace=_workspace(),
            portfolio_id=_PORTFOLIO_ID,
            user_id=1,
            reason=_GOOD_REASON,
        )


async def test_clearing_a_frozen_book_releases_it_and_logs_the_override() -> None:
    portfolio = _portfolio(frozen=True)
    session = AsyncMock()
    session.add = MagicMock()  # add() is synchronous on a real session
    # First scalar() resolves the portfolio; the second is the decision-ledger sequence lookup.
    session.scalar.side_effect = [portfolio, 7]
    session.scalars.return_value = [_snapshot()]

    await clear_shadow_ladder_freeze(
        session,
        workspace=_workspace(),
        portfolio_id=_PORTFOLIO_ID,
        user_id=99,
        reason=_GOOD_REASON,
    )

    assert portfolio.configuration["ladder_frozen"] is False
    # The override must be appended to the ledger, carrying its written justification.
    added = [call.args[0] for call in session.add.call_args_list]
    events = [obj for obj in added if getattr(obj, "event_type", None) == "risk"]
    assert len(events) == 1
    event = events[0]
    assert event.payload["action"] == "drawdown_ladder_freeze_cleared"
    assert event.payload["reason"] == _GOOD_REASON
    assert event.payload["cleared_by_user_id"] == 99
    assert event.sequence == 8  # one past the existing maximum
