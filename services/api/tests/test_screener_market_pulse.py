"""Pure checks for institutional market-pulse helpers."""

from __future__ import annotations

from api.routers.screener import _index_pct_from_points, _risk_mode


def test_index_pct_from_points_converts_dsex_points_to_percent():
    # MarketSummary.dsex_change is stored as index points, not percent.
    assert _index_pct_from_points(5722.54, 2.77) == 0.05


def test_index_pct_from_points_omits_implausible_index_moves():
    assert _index_pct_from_points(100, 50) is None


def test_risk_mode_uses_index_breadth_and_turnover():
    assert _risk_mode(0.3, 1.1, adv=70, dec=30) == "risk_on"
    assert _risk_mode(-0.3, 0.8, adv=30, dec=70) == "defensive"
    assert _risk_mode(0.1, 0.7, adv=55, dec=45) == "mixed"
