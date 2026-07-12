"""Scanner board metadata — pure unit tests (evidence labels, regime logic, tab layout)."""

from __future__ import annotations

from api.routers.company import FinancialHealth
from api.routers.scanner import (
    _EVIDENCE,
    _REGIME_SENSITIVE,
    _TABS,
    _cashflow_quality_margin,
    _financial_risk_flags,
    regime_from,
    scanner_pack_for,
)


def test_scanner_universe_is_pinned_to_latest_analytics_date() -> None:
    from api.routers.scanner import _clean_codes

    sql = str(_clean_codes("DSE")).lower()
    assert "max(" in sql
    assert "as_of_date" in sql


def test_every_tab_board_carries_an_evidence_label() -> None:
    """Truth-in-labeling: no board reaches the Ideas page without declaring its evidence class."""
    for tab, keys in _TABS.items():
        for key in keys:
            assert key in _EVIDENCE, f"board {key!r} on tab {tab!r} has no evidence label"
            assert _EVIDENCE[key] in {"backtested", "framework", "utility"}


def test_evidence_classes_match_the_research() -> None:
    # Backtested = validated on our DSE data (Scheme-3, trending backtest, factor study).
    assert _EVIDENCE["quality_reversal"] == "backtested"
    assert _EVIDENCE["oversold_quality"] == "backtested"
    assert _EVIDENCE["active_today"] == "backtested"
    # Lenses are classic frameworks — locally the value factor was flat, momentum negative.
    assert all(_EVIDENCE[k] == "framework" for k in _TABS["lens"])
    # Value tab claims usefulness, not edge.
    assert all(_EVIDENCE[k] == "utility" for k in _TABS["value"])


def test_regime_sensitive_boards_are_the_reversal_family() -> None:
    assert set(_REGIME_SENSITIVE) == {"quality_reversal", "oversold_quality"}
    # Every regime-sensitive board must actually be served on a tab (the banner must be reachable).
    served = {k for keys in _TABS.values() for k in keys}
    assert served >= _REGIME_SENSITIVE


def test_regime_from() -> None:
    assert regime_from(5800.0, 5600.0) == "above_200dma"
    assert regime_from(5400.0, 5600.0) == "below_200dma"
    assert regime_from(5600.0, 5600.0) == "above_200dma"  # touching counts as above


def test_oversold_board_is_on_today_tab_after_the_flagship() -> None:
    today = _TABS["today"]
    assert today.index("quality_reversal") < today.index("oversold_quality")


def test_us_pack_is_eod_and_does_not_reuse_dse_reversal_claims() -> None:
    pack = scanner_pack_for("US")
    assert pack.key == "us-eod-research-v1"
    keys = {key for tab in pack.tabs for key in tab.boards}
    assert {
        "us_relative_strength",
        "us_unusual_volume",
        "us_recent_filings",
        "us_cashflow_quality",
        "us_financial_risk",
        "institutional_13f_accumulation",
        "institutional_13f_distribution",
    } == keys
    assert keys.isdisjoint({"quality_reversal", "oversold_quality", "active_today"})
    assert pack.home_boards == (
        "us_relative_strength",
        "us_recent_filings",
        "institutional_13f_accumulation",
        "us_financial_risk",
    )


def test_cashflow_quality_requires_positive_cash_and_profit_margins() -> None:
    strong = FinancialHealth(
        revenue_ttm_mn=1_000,
        free_cash_flow_ttm_mn=120,
        profit_margin_pct=15,
    )
    assert _cashflow_quality_margin(strong) == 12
    assert (
        _cashflow_quality_margin(
            FinancialHealth(
                revenue_ttm_mn=1_000,
                free_cash_flow_ttm_mn=-20,
                profit_margin_pct=15,
            )
        )
        is None
    )


def test_financial_risk_flags_are_explicit_and_exclude_financial_sectors() -> None:
    health = FinancialHealth(
        current_ratio=0.8,
        debt_to_equity=2.1,
        free_cash_flow_ttm_mn=-50,
    )
    assert _financial_risk_flags(health, "Industrials") == [
        "current ratio 0.80",
        "debt/equity 2.10x",
        "negative FCF $50mn",
    ]
    assert _financial_risk_flags(health, "Financials") == []
