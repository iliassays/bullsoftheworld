"""Scanner board metadata — pure unit tests (evidence labels, regime logic, tab layout)."""

from __future__ import annotations

from api.routers.scanner import _EVIDENCE, _REGIME_SENSITIVE, _TABS, regime_from


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
