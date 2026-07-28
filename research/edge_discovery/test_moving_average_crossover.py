from __future__ import annotations

import datetime as dt

from research.edge_discovery.moving_average_crossover import (
    MovingAverageBar,
    MovingAverageCrossoverSpec,
    moving_average_series,
    scan_bullish_crossover_trades,
)


def _bars(
    closes: list[float],
    *,
    opens: list[float] | None = None,
    volume: float = 100_000,
) -> list[MovingAverageBar]:
    opens = opens or closes
    return [
        MovingAverageBar(
            date=dt.date(2026, 1, 1) + dt.timedelta(days=index),
            open=opens[index],
            high=max(opens[index], close) + 0.2,
            low=min(opens[index], close) - 0.2,
            close=close,
            raw_close=close,
            volume=volume,
        )
        for index, close in enumerate(closes)
    ]


def _spec(**overrides) -> MovingAverageCrossoverSpec:
    values = {
        "key": "test",
        "fast_period": 2,
        "slow_period": 4,
        "regime_period": 6,
        "slope_lookback": 1,
        "atr_period": 2,
        "maximum_extension_atr": 10.0,
        "maximum_holding_sessions": 4,
        "turnover_period": 2,
        "minimum_price": 1.0,
        "minimum_average_turnover": 1.0,
    }
    values.update(overrides)
    return MovingAverageCrossoverSpec(**values)


def test_series_is_prefix_causal() -> None:
    original = _bars([10, 9, 8, 8, 8, 9, 10, 11])
    extended = [
        *original,
        MovingAverageBar(
            date=dt.date(2026, 1, 9),
            open=100,
            high=101,
            low=99,
            close=100,
            raw_close=100,
            volume=100_000,
        )
    ]
    first = moving_average_series(original, _spec())
    second = moving_average_series(extended, _spec())
    assert second.fast[: len(original)] == first.fast
    assert second.slow[: len(original)] == first.slow
    assert second.regime[: len(original)] == first.regime


def test_signal_and_exit_fill_at_following_opens() -> None:
    closes = [10, 9, 8, 8, 8, 10, 11, 12, 8, 8, 8, 8]
    opens = [10, 9, 8, 8, 8, 10, 11, 13, 12, 7, 8, 8]
    trades = scan_bullish_crossover_trades(
        "TEST",
        _bars(closes, opens=opens),
        spec=_spec(),
        normal_one_way_cost=0.01,
        stressed_one_way_cost=0.02,
    )
    assert len(trades) == 1
    trade = trades[0]
    assert trade.signal_date == dt.date(2026, 1, 6)
    assert trade.entry_date == dt.date(2026, 1, 7)
    assert trade.entry_open == 11
    assert trade.exit_signal_date == dt.date(2026, 1, 9)
    assert trade.exit_date == dt.date(2026, 1, 10)
    assert trade.exit_open == 7
    assert trade.normal_return < trade.gross_return
    assert trade.stressed_return < trade.normal_return


def test_extension_guard_rejects_late_jump() -> None:
    closes = [10, 9, 8, 8, 8, 9, 30, 31, 32, 33, 34, 35]
    assert (
        scan_bullish_crossover_trades(
            "EXTENDED",
            _bars(closes),
            spec=_spec(maximum_extension_atr=0.25),
            normal_one_way_cost=0,
            stressed_one_way_cost=0,
        )
        == []
    )


def test_continuing_bullish_state_does_not_duplicate_entry() -> None:
    closes = [10, 9, 8, 8, 8, 10, 11, 12, 13, 14, 15, 16, 17, 18]
    trades = scan_bullish_crossover_trades(
        "ONE",
        _bars(closes),
        spec=_spec(maximum_holding_sessions=4),
        normal_one_way_cost=0,
        stressed_one_way_cost=0,
    )
    assert len(trades) == 1


def test_incomplete_timeout_is_not_reported() -> None:
    closes = [10, 9, 8, 8, 8, 9, 11, 12]
    assert (
        scan_bullish_crossover_trades(
            "OPEN",
            _bars(closes),
            spec=_spec(maximum_holding_sessions=4),
            normal_one_way_cost=0,
            stressed_one_way_cost=0,
        )
        == []
    )
