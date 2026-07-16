import datetime as dt

import pytest

from bulls.analytics import Snapshot
from bulls.core.models import AgentPortfolio
from ingestion.agent_trader import (
    _minimum_executable_cash,
    _observe_blocked_opportunity,
    _resolve_opportunity,
)


def _snapshot(price: float, minute: int) -> Snapshot:
    return Snapshot(
        code="TEST",
        sector="Test",
        category="A",
        ltp=price,
        change_pct=0.0,
        quote_as_of=dt.datetime(2026, 7, 16, 5, minute, tzinfo=dt.UTC),
        last_close=price,
        rsi_14=35.0,
        pct_from_52w_high=-45.0,
        pct_from_52w_low=10.0,
        pe_ratio=8.0,
        pb_ratio=1.0,
        pe_vs_sector=0.6,
        roe=15.0,
        eps_growth_yoy=5.0,
        dividend_yield=3.0,
        volatility=20.0,
        cmf_20=0.2,
        obv_slope=0.1,
        institute_delta=1.0,
        foreign_delta=0.0,
        rel_volume_5d=1.5,
        relative_volume=1.5,
        avg_volume_20=100_000,
        market_cap_mn=1_000,
    )


def test_blocked_opportunity_keeps_one_episode_and_price_path() -> None:
    agent = AgentPortfolio(
        user_id=7,
        market="DSE",
        strategy="value",
        initial_capital=100_000,
        cash_settled=4_000,
    )
    first_at = dt.datetime(2026, 7, 16, 5, 3, tzinfo=dt.UTC)
    opportunity = _observe_blocked_opportunity(
        None,
        tenant_id="bullsofdhaka",
        agent=agent,
        snap=_snapshot(100.0, 0),
        observed_at=first_at,
        signal_reason="qualifies",
        block_reason="no_cash",
        rank=4,
        target_budget=15_000,
        available_cash=4_000,
        pending_cash=10_000,
        free_slots=2,
    )
    assert opportunity.blocked_ticks == 1
    assert opportunity.no_cash_ticks == 1
    assert opportunity.first_price == 100
    assert opportunity.required_cash == pytest.approx(5_020)

    second_at = dt.datetime(2026, 7, 16, 5, 18, tzinfo=dt.UTC)
    same = _observe_blocked_opportunity(
        opportunity,
        tenant_id="bullsofdhaka",
        agent=agent,
        snap=_snapshot(110.0, 15),
        observed_at=second_at,
        signal_reason="still qualifies",
        block_reason="no_slot",
        rank=2,
        target_budget=15_000,
        available_cash=20_000,
        pending_cash=0,
        free_slots=0,
    )
    assert same is opportunity
    assert opportunity.blocked_ticks == 2
    assert opportunity.no_cash_ticks == 1
    assert opportunity.no_slot_ticks == 1
    assert opportunity.best_rank == 2
    assert opportunity.best_price == 110
    assert opportunity.worst_price == 100
    assert opportunity.last_available_cash == 20_000

    _resolve_opportunity(
        opportunity,
        status="entered",
        observed_at=dt.datetime(2026, 7, 16, 5, 33, tzinfo=dt.UTC),
        snap=_snapshot(105.0, 30),
    )
    assert opportunity.status == "entered"
    assert opportunity.resolved_price == 105
    assert opportunity.best_price == 110
    assert opportunity.resolved_at is not None


def test_minimum_executable_cash_respects_integer_shares_and_fee() -> None:
    assert _minimum_executable_cash(100.0) == pytest.approx(5_020.0)
    assert _minimum_executable_cash(6_000.0) == pytest.approx(6_024.0)
