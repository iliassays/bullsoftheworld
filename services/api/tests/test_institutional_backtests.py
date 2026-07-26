from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from api.institutional_research.institutional_backtests import (
    _adjusted_bar,
    _bars,
    _delay_schedule,
    prepare_institutional_backtest,
)
from api.institutional_research.schemas import BacktestRequest
from api.institutional_research.workflow import _stable_hash


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


def test_evidence_hash_canonicalizes_date_keyed_schedules() -> None:
    as_of = dt.date(2026, 1, 2)

    assert _stable_hash({as_of: {"AAA": 0.5}}) == _stable_hash(
        {as_of.isoformat(): {"AAA": 0.5}}
    )


@pytest.mark.parametrize(
    "strategy_key",
    [
        "dse_compression_breakout_20d_v1",
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


def _bar_row(
    code: str,
    *,
    day: dt.date,
    adjusted_close: float | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        code=code,
        date=day,
        open=10.0,
        high=11.0,
        low=9.0,
        close=10.0,
        volume=1_000,
        adjusted_close=adjusted_close,
    )


def test_adjusted_bar_rejects_non_positive_economic_prices() -> None:
    assert _adjusted_bar(
        _bar_row(
            "BAD",
            day=dt.date(2026, 1, 2),
            adjusted_close=-10.0,
        )
    ) is None


class _RowsSession:
    def __init__(self, rows) -> None:
        self.rows = rows

    async def scalars(self, _statement):
        return self.rows


async def test_bar_adapter_excludes_the_whole_security_when_history_is_corrupt() -> None:
    day = dt.date(2026, 1, 2)
    session = _RowsSession(
        [
            _bar_row("BAD", day=day, adjusted_close=10.0),
            _bar_row("BAD", day=day + dt.timedelta(days=1), adjusted_close=0.0),
            _bar_row("GOOD", day=day, adjusted_close=10.0),
        ]
    )

    bars = await _bars(
        session,
        codes=["BAD", "GOOD"],
        start=day,
        end=day + dt.timedelta(days=1),
    )

    assert set(bars) == {"GOOD"}


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
