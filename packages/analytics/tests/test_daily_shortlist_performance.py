from __future__ import annotations

import datetime as dt

import pytest

from bulls.analytics.daily_shortlist_performance import (
    BenchmarkClose,
    ShortlistAppearance,
    ShortlistPriceBar,
    evaluate_shortlist_performance,
    independent_episodes,
)


def _date(day: int) -> dt.date:
    return dt.date(2026, 7, day)


def _bar(
    code: str,
    day: int,
    *,
    open_: float,
    close: float,
    high: float | None = None,
    low: float | None = None,
) -> ShortlistPriceBar:
    return ShortlistPriceBar(
        code=code,
        date=_date(day),
        open=open_,
        high=max(open_, close) if high is None else high,
        low=min(open_, close) if low is None else low,
        close=close,
    )


def _bench(days: range) -> list[BenchmarkClose]:
    return [BenchmarkClose(date=_date(day), close=1000 + day * 10) for day in days]


def test_horizons_use_market_sessions_and_do_not_skip_a_missing_stock_bar():
    appearances = [
        ShortlistAppearance("AAA", _date(10), 100.0, 1, "forward"),
    ]
    bars = [
        _bar("AAA", 10, open_=99, close=100),
        # Missing on market session 11. Session 12 must not be relabelled as "1S".
        _bar("AAA", 12, open_=102, close=103),
        _bar("AAA", 13, open_=103, close=104),
        _bar("AAA", 14, open_=104, close=105),
        _bar("AAA", 15, open_=105, close=106),
        _bar("AAA", 16, open_=106, close=107),
        _bar("AAA", 17, open_=107, close=108),
        _bar("AAA", 18, open_=108, close=109),
        _bar("AAA", 19, open_=109, close=110),
        _bar("AAA", 20, open_=110, close=111),
    ]
    report = evaluate_shortlist_performance(
        appearances=appearances,
        bars=bars,
        benchmark=_bench(range(10, 21)),
    )
    metrics = report.cohorts[0].horizons

    assert metrics[0].sessions == 1
    assert metrics[0].matured_appearances == 1
    assert metrics[0].observations == 0
    assert metrics[0].missing_bar_appearances == 1
    assert metrics[1].sessions == 3
    assert metrics[1].mean_return_pct == pytest.approx(4.0)


def test_performance_separates_follow_through_from_next_open_execution_proxy():
    appearances = [
        ShortlistAppearance("AAA", _date(10), 100.0, 1, "forward"),
    ]
    bars = [
        _bar("AAA", 9, open_=98, close=99),
        _bar("AAA", 10, open_=99, close=100),
        _bar("AAA", 11, open_=105, close=110, high=112, low=104),
        _bar("AAA", 12, open_=111, close=108),
        _bar("AAA", 13, open_=108, close=115),
        _bar("AAA", 14, open_=115, close=116),
        _bar("AAA", 15, open_=116, close=120),
        _bar("AAA", 16, open_=120, close=121),
        _bar("AAA", 17, open_=121, close=122),
        _bar("AAA", 18, open_=122, close=123),
        _bar("AAA", 19, open_=123, close=124),
        _bar("AAA", 20, open_=124, close=125),
    ]
    report = evaluate_shortlist_performance(
        appearances=appearances,
        bars=bars,
        benchmark=_bench(range(9, 21)),
    )
    one_session = report.cohorts[0].horizons[0]

    assert one_session.mean_return_pct == pytest.approx(10.0)
    assert one_session.next_open_mean_return_pct == pytest.approx(4.762)
    assert one_session.mean_benchmark_return_pct == pytest.approx(0.909)
    assert one_session.mean_excess_return_pct == pytest.approx(9.091)


def test_limit_locked_next_open_is_excluded_but_follow_through_remains():
    appearance = ShortlistAppearance("AAA", _date(10), 100.0, 1, "forward")
    bars = [
        _bar("AAA", 10, open_=99, close=100),
        _bar("AAA", 11, open_=108, close=108, high=108.1, low=108.0),
    ]
    report = evaluate_shortlist_performance(
        appearances=[appearance],
        bars=bars,
        benchmark=_bench(range(10, 12)),
    )
    metric = report.cohorts[0].horizons[0]

    assert metric.mean_return_pct == pytest.approx(8.0)
    assert metric.limit_locked_entries == 1
    assert metric.next_open_observations == 0
    assert metric.next_open_mean_return_pct is None


def test_suspicious_price_path_is_reported_and_excluded():
    appearance = ShortlistAppearance("AAA", _date(10), 100.0, 1, "reconstructed")
    bars = [
        _bar("AAA", 10, open_=100, close=100),
        _bar("AAA", 11, open_=50, close=50),
    ]
    report = evaluate_shortlist_performance(
        appearances=[appearance],
        bars=bars,
        benchmark=_bench(range(10, 12)),
    )
    metric = report.cohorts[0].horizons[0]

    assert metric.matured_appearances == 1
    assert metric.observations == 0
    assert metric.suspicious_price_paths == 1


def test_missing_benchmark_does_not_hide_valid_ticker_follow_through():
    appearance = ShortlistAppearance("AAA", _date(10), 100.0, 1, "forward")
    bars = [
        _bar("AAA", 10, open_=100, close=100),
        _bar("AAA", 11, open_=101, close=105),
    ]
    report = evaluate_shortlist_performance(
        appearances=[appearance],
        bars=bars,
        benchmark=[],
        market_dates=[_date(10), _date(11)],
    )
    metric = report.cohorts[0].horizons[0]

    assert metric.observations == 1
    assert metric.mean_return_pct == pytest.approx(5.0)
    assert metric.benchmark_observations == 0
    assert metric.mean_benchmark_return_pct is None
    assert metric.mean_excess_return_pct is None


def test_repeated_appearances_are_one_episode_inside_ten_market_sessions():
    appearances = [
        ShortlistAppearance("AAA", _date(10), 100, 1, "reconstructed"),
        ShortlistAppearance("AAA", _date(11), 101, 1, "reconstructed"),
        ShortlistAppearance("AAA", _date(20), 102, 1, "forward"),
        ShortlistAppearance("BBB", _date(11), 50, 2, "forward"),
    ]
    market_dates = [_date(day) for day in range(1, 22)]

    episodes = independent_episodes(appearances, market_dates)

    assert [(item.code, item.as_of) for item in episodes] == [
        ("AAA", _date(10)),
        ("BBB", _date(11)),
    ]


def test_continuous_repeat_chain_remains_one_episode():
    appearances = [
        ShortlistAppearance("AAA", _date(2), 100, 1, "reconstructed"),
        ShortlistAppearance("AAA", _date(8), 101, 1, "reconstructed"),
        ShortlistAppearance("AAA", _date(14), 102, 1, "reconstructed"),
        ShortlistAppearance("AAA", _date(20), 103, 1, "forward"),
    ]

    episodes = independent_episodes(appearances, [_date(day) for day in range(1, 22)])

    assert [(item.code, item.as_of) for item in episodes] == [("AAA", _date(2))]
