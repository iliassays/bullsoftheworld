"""Unit tests for the daily valuation derivation."""

from __future__ import annotations

from bulls.analytics import compute_valuation


def test_full_valuation():
    # PRAGATIINS-like: close 83.2, 81,214,559 shares, EPS 5.31, NAV 57.36, 27% cash div, face 10.
    v = compute_valuation(
        83.2,
        outstanding_shares=81_214_559,
        market_cap_mn_ref=6147.942,
        free_float_mcap_mn_ref=3579.915,
        eps=5.31,
        nav_per_share=57.36,
        cash_dividend_pct=27.0,
        face_value=10.0,
    )
    assert v.market_cap_mn == round(83.2 * 81_214_559 / 1e6, 2)  # ~6757.05
    assert v.pe_ratio == round(83.2 / 5.31, 2)  # ~15.67
    assert v.pb_ratio == round(83.2 / 57.36, 2)  # ~1.45
    # 27% of face 10 = 2.7 taka; yield = 2.7 / 83.2 * 100
    assert v.dividend_yield == round(2.7 / 83.2 * 100, 2)  # ~3.25
    # free-float cap scales today's market cap by the (stable) float ratio
    assert v.free_float_cap_mn == round(v.market_cap_mn * (3579.915 / 6147.942), 2)


def test_negative_eps_yields_no_pe():
    # Loss-making (1JANATAMF-like EPS -2.24): P/E is meaningless, must be None — not negative.
    v = compute_valuation(8.0, eps=-2.24, nav_per_share=7.54)
    assert v.pe_ratio is None
    assert v.pb_ratio == round(8.0 / 7.54, 2)


def test_missing_fundamentals_degrade_gracefully():
    # Only price known (no profile): everything None, no crash.
    v = compute_valuation(100.0)
    assert v.market_cap_mn is None
    assert v.pe_ratio is None and v.dividend_yield is None


def test_nonpositive_close_returns_empty():
    v = compute_valuation(0.0, outstanding_shares=1_000_000, eps=5.0)
    assert v.market_cap_mn is None and v.pe_ratio is None


def test_yield_trap_is_omitted():
    # UNIONBANK-like: 5% cash on face 10 = 0.5 taka, but price collapsed to 1.5 -> 33% trailing yield.
    # That's a price-collapse trap, not income — omit rather than mislead.
    v = compute_valuation(1.5, cash_dividend_pct=5.0, face_value=10.0)
    assert v.dividend_yield is None


def test_high_but_sane_yield_kept():
    # ~9% cash yield (face 10, 9% cash, price ~10) is plausible income — keep it.
    v = compute_valuation(10.0, cash_dividend_pct=9.0, face_value=10.0)
    assert v.dividend_yield == round(0.9 / 10.0 * 100, 2)  # 9.0
