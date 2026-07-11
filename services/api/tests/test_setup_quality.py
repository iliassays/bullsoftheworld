"""_setup_quality() — the Clean/Mixed/High-risk read badge shown on every Ideas/Markets row.

Regression for a 2026-07-05 user report: "Cheap vs sector" (value_vs_sector) showed "Mixed read"
on every single row, even for deep-liquidity Category-A stocks with zero risk flags. Root cause:
value_vs_sector was missing from the Clean-read-eligible screen whitelist, even though it's the
same shape as quality_roe (already whitelisted) — a plain value ranking with no catalyst concept.
"""

from __future__ import annotations

from api.routers.screener import ScreenItem, ScreenOut, _setup_quality


def _screen(key: str) -> ScreenOut:
    return ScreenOut(key=key, title="t", description="d", value_label="v", items=[])


def _item(**kw) -> ScreenItem:
    defaults = {"code": "TEST", "last_close": 100.0, "value": 1.0}
    defaults.update(kw)
    return ScreenItem(**defaults)


def test_deep_liquidity_value_vs_sector_is_clean_not_mixed():
    """The exact reported case: a Category-A stock with adtv well above the clean threshold,
    no pump note, on the 'Cheap vs sector' screen — must be able to read Clean."""
    screen = _screen("value_vs_sector")
    item = _item(category="A", adtv_mn=54.2, note=None)
    assert _setup_quality(screen, item) == "Screen checks met"


def test_thin_liquidity_value_vs_sector_stays_mixed():
    # Above the High-risk liquidity floor (5mn) but below the Clean threshold (20mn) — the
    # genuine "needs a second look" middle ground, distinct from both other tiers.
    screen = _screen("value_vs_sector")
    item = _item(category="A", adtv_mn=10.0, note=None)
    assert _setup_quality(screen, item) == "Mixed evidence"


def test_z_category_is_always_high_risk_even_with_deep_liquidity():
    screen = _screen("value_vs_sector")
    item = _item(category="Z", adtv_mn=100.0, note=None)
    assert _setup_quality(screen, item) == "High-risk read"


def test_sponsor_selling_never_reads_clean_even_with_deep_liquidity():
    """Deliberately excluded: 'Clean read' renders with a green/positive tone in the UI, which
    would send the wrong signal on a cautionary insider-selling board."""
    screen = _screen("sponsor_selling")
    item = _item(category="A", adtv_mn=100.0, note=None)
    assert _setup_quality(screen, item) != "Screen checks met"


def test_institutional_selling_never_reads_clean_even_with_deep_liquidity():
    """Same reasoning as sponsor_selling: institutional distribution is a cautionary board, so
    it should never get sponsor_selling's exemption — added alongside sponsor_selling
    2026-07-05 after a user asked why only sponsors got a 'selling' board."""
    screen = _screen("institutional_selling")
    item = _item(category="A", adtv_mn=100.0, note=None)
    assert _setup_quality(screen, item) != "Screen checks met"


def test_screen_without_catalyst_or_whitelist_membership_is_mixed():
    screen = _screen("some_screen_not_in_the_whitelist")
    item = _item(category="A", adtv_mn=100.0, note=None)
    assert _setup_quality(screen, item) == "Mixed evidence"
