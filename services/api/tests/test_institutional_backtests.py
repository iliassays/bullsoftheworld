from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.dialects import postgresql

from api.institutional_research.institutional_backtests import (
    _bars,
    _delay_schedule,
    prepare_institutional_backtest,
)
from api.institutional_research.schemas import BacktestRequest


def test_event_placebo_moves_each_change_by_completed_sessions() -> None:
    sessions = [dt.date(2026, 1, 2) + dt.timedelta(days=index) for index in range(40)]
    schedule = {
        sessions[3]: {"A": 0.05},
        sessions[10]: {"A": 0.025},
    }

    delayed = _delay_schedule(schedule, sessions=sessions, delay_sessions=21)

    assert delayed == {
        sessions[24]: {"A": 0.05},
        sessions[31]: {"A": 0.025},
    }


def test_event_placebo_refuses_non_positive_delay() -> None:
    with pytest.raises(ValueError, match="at least one"):
        _delay_schedule({}, sessions=[], delay_sessions=0)


@pytest.mark.parametrize(
    "strategy_key",
    [
        "us_activist_13d_v1",
        "us_insider_cluster_v1",
        "us_forced_seller_v1",
        "us_factor_sleeve_v1",
    ],
)
def test_schema_accepts_registered_institutional_strategy_keys(strategy_key: str) -> None:
    request = BacktestRequest(
        idempotency_key=f"test-{strategy_key}",
        strategy_key=strategy_key,
    )

    assert request.strategy_key == strategy_key


class _CapturingSession:
    statement = None

    async def scalars(self, statement):
        self.statement = statement
        return []


async def test_institutional_bar_adapter_is_hard_bound_to_us_market() -> None:
    session = _CapturingSession()

    bars = await _bars(
        session,
        codes=["USONLY"],
        start=dt.date(2025, 1, 1),
        end=dt.date(2026, 1, 1),
    )

    assert bars == {}
    sql = str(
        session.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "daily_bars.market = 'US'" in sql
    assert "'DSE'" not in sql


async def test_system_b_fails_closed_without_querying_proxy_datasets() -> None:
    request = BacktestRequest(
        idempotency_key="system-b-readiness",
        strategy_key="us_forced_seller_v1",
        start_date=dt.date(2025, 1, 1),
        end_date=dt.date(2026, 1, 1),
    )

    preparation = await prepare_institutional_backtest(
        _CapturingSession(),
        strategy_key=request.strategy_key,
        request=request,
    )

    assert preparation.securities == []
    assert preparation.weight_schedule == {}
    assert preparation.diagnostics["readiness"]["status"] == "data_blocked"
    assert len(preparation.failed_gates) == 7
