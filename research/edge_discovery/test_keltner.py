from __future__ import annotations

import datetime as dt

import pytest

from research.edge_discovery.keltner import (
    KeltnerBar,
    KeltnerSpec,
    keltner_bar_issue,
    keltner_channels,
    scan_keltner_trades,
)


def _bars(
    closes: list[float],
    *,
    opens: list[float] | None = None,
    volume: float = 100_000,
    start: dt.date = dt.date(2026, 1, 1),
) -> list[KeltnerBar]:
    opens = opens or closes
    return [
        KeltnerBar(
            date=start + dt.timedelta(days=index),
            open=opens[index],
            high=max(opens[index], close) + 0.5,
            low=min(opens[index], close) - 0.5,
            close=close,
            raw_close=close,
            volume=volume,
        )
        for index, close in enumerate(closes)
    ]


def _spec(**overrides) -> KeltnerSpec:
    values = {
        "key": "test",
        "ema_period": 3,
        "atr_period": 3,
        "atr_multiple": 0.5,
        "maximum_holding_sessions": 5,
        "turnover_period": 3,
        "minimum_price": 1.0,
        "minimum_average_turnover": 1.0,
    }
    values.update(overrides)
    return KeltnerSpec(**values)


def test_channels_are_prefix_causal() -> None:
    original = _bars([10, 10, 10, 11, 12, 13])
    extended = original + _bars([100, 120], start=dt.date(2026, 1, 7))
    first = keltner_channels(original, _spec())
    second = keltner_channels(extended, _spec())
    assert second.middle[: len(original)] == first.middle
    assert second.atr[: len(original)] == first.atr
    assert second.upper[: len(original)] == first.upper


def test_long_signal_enters_and_exits_at_following_opens() -> None:
    closes = [10, 10, 10, 10, 13, 14, 9, 9, 9]
    opens = [10, 10, 10, 10, 13, 15, 14, 8, 9]
    trades = scan_keltner_trades(
        "LONG",
        _bars(closes, opens=opens),
        spec=_spec(),
        direction="long",
        normal_one_way_cost=0.01,
        stressed_one_way_cost=0.02,
    )
    assert len(trades) == 1
    trade = trades[0]
    assert trade.signal_date == dt.date(2026, 1, 5)
    assert trade.entry_date == dt.date(2026, 1, 6)
    assert trade.entry_open == 15
    assert trade.exit_signal_date == dt.date(2026, 1, 7)
    assert trade.exit_date == dt.date(2026, 1, 8)
    assert trade.exit_open == 8
    assert trade.normal_return < trade.gross_return
    assert trade.stressed_return < trade.normal_return


def test_continuing_outside_channel_does_not_duplicate_position() -> None:
    closes = [10, 10, 10, 10, 13, 14, 15, 16, 17, 9, 9, 9]
    trades = scan_keltner_trades(
        "ONE",
        _bars(closes),
        spec=_spec(maximum_holding_sessions=7),
        direction="long",
        normal_one_way_cost=0,
        stressed_one_way_cost=0,
    )
    assert len(trades) == 1


def test_short_return_uses_next_open_cover() -> None:
    closes = [10, 10, 10, 10, 7, 6, 11, 11, 11]
    opens = [10, 10, 10, 10, 7, 6, 7, 12, 11]
    trades = scan_keltner_trades(
        "SHORT",
        _bars(closes, opens=opens),
        spec=_spec(),
        direction="short",
        normal_one_way_cost=0,
        stressed_one_way_cost=0,
    )
    assert len(trades) == 1
    assert trades[0].entry_open == 6
    assert trades[0].exit_open == 12
    assert trades[0].gross_return == pytest.approx(-1.0)


def test_dse_style_jump_filter_rejects_contaminated_episode() -> None:
    closes = [10, 10, 10, 10, 15, 16, 9, 9, 9]
    assert (
        scan_keltner_trades(
            "DIRTY",
            _bars(closes),
            spec=_spec(maximum_close_jump=0.35),
            direction="long",
            normal_one_way_cost=0,
            stressed_one_way_cost=0,
        )
        == []
    )


def test_incomplete_timeout_is_not_reported() -> None:
    closes = [10, 10, 10, 10, 13, 14, 15]
    assert (
        scan_keltner_trades(
            "OPEN",
            _bars(closes),
            spec=_spec(maximum_holding_sessions=5),
            direction="long",
            normal_one_way_cost=0,
            stressed_one_way_cost=0,
        )
        == []
    )


def test_invalid_ohlc_bar_is_classified_without_repair() -> None:
    bar = KeltnerBar(
        date=dt.date(2026, 7, 24),
        open=43.58,
        high=43.15,
        low=42.20,
        close=42.33,
        raw_close=42.33,
        volume=100_000,
    )
    assert keltner_bar_issue(bar) == "invalid_ohlc_range"
    with pytest.raises(ValueError, match="invalid OHLC"):
        keltner_channels([bar], _spec())
