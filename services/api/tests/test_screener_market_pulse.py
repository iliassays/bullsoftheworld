"""Pure checks for institutional market-pulse helpers."""

from __future__ import annotations

from api.routers.screener import (
    _index_pct_from_points,
    _intraday_risk_mode,
    _risk_mode,
    _select_live_turnover,
    _turnover_ratio,
)


def test_index_pct_from_points_converts_dsex_points_to_percent():
    # MarketSummary.dsex_change is stored as index points, not percent.
    assert _index_pct_from_points(5722.54, 2.77) == 0.05


def test_index_pct_from_points_omits_implausible_index_moves():
    assert _index_pct_from_points(100, 50) is None


def test_risk_mode_uses_index_breadth_and_turnover():
    assert _risk_mode(0.3, 1.1, adv=70, dec=30) == "risk_on"
    assert _risk_mode(-0.3, 0.8, adv=30, dec=70) == "defensive"
    assert _risk_mode(0.1, 0.7, adv=55, dec=45) == "mixed"


def test_intraday_risk_mode_does_not_reuse_previous_index_move():
    assert _intraday_risk_mode(adv=60, dec=40) == "risk_on"
    assert _intraday_risk_mode(adv=40, dec=60) == "defensive"
    assert _intraday_risk_mode(adv=50, dec=50) == "mixed"


def test_turnover_ratio_uses_completed_sessions_as_baseline():
    assert _turnover_ratio(50.0, [100.0, 100.0, 100.0]) == 0.5
    assert _turnover_ratio(50.0, []) is None
    assert _turnover_ratio(None, [100.0]) is None


def test_live_turnover_prefers_exchange_reported_value_with_full_coverage():
    assert _select_live_turnover(1_234.5, 99, 100, 1_250.0) == (1_234.5, False)


def test_live_turnover_marks_low_coverage_fallback_as_estimated():
    assert _select_live_turnover(900.0, 90, 100, 1_250.0) == (1_250.0, True)
