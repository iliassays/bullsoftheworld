"""Unit tests for the deterministic Plain read synthesis."""

from __future__ import annotations

from bulls.analytics import build_plain_read


def test_quality_steady_uptrend_profile():
    r = build_plain_read(
        code="SQURPHARMA",
        as_of_date="2026-06-27",
        market_cap_mn=200000,
        adtv_mn=14.0,
        above_sma_200=True,
        mom_12_1=30.0,
        volatility=13.0,
        roe=35.0,
        pe_ratio=18.0,
        pe_vs_sector=0.9,
        dividend_yield=2.0,
        rsi_14=72.0,
        pct_from_52w_high=-2.0,
        cmf_20=0.18,
    )
    tags = {p.tag for p in r.points}
    assert {"size", "trend", "steadiness", "quality", "shortterm"} <= tags
    assert "uptrend" in r.headline.lower()
    assert "stretched" in r.headline.lower()  # RSI 72
    # stretched profile should suggest waiting for a pullback, never "buy"
    assert "pullback" in r.how_to_read.lower()
    assert "buy" not in r.how_to_read.lower() and "sell" not in r.how_to_read.lower()


def test_bangla_locale_renders_and_stays_descriptive():
    r = build_plain_read(
        code="SQURPHARMA",
        as_of_date="2026-06-27",
        locale="bn",
        market_cap_mn=200000,
        adtv_mn=14.0,
        above_sma_200=True,
        roe=35.0,
        volatility=13.0,
        dividend_yield=6.0,
    )
    text = r.headline + " " + " ".join(p.text for p in r.points) + " " + r.how_to_read
    assert any("ঀ" <= ch <= "৿" for ch in text)  # contains Bangla characters
    assert "পরামর্শ" not in text  # no advice wording leaked into the body
    assert "সুপারিশ নয়" in r.disclaimer  # "not a recommendation" in Bangla
    # never English buy/sell either
    assert "buy" not in text.lower() and "sell" not in text.lower()


def test_nulls_are_omitted_not_guessed():
    r = build_plain_read(code="X", as_of_date="2026-06-27", above_sma_200=None)
    assert all(p.text for p in r.points)
    assert "recommendation" in r.disclaimer.lower()


def test_lossmaking_is_stated_plainly():
    r = build_plain_read(code="X", as_of_date="2026-06-27", roe=-12.0)
    quality = next(p for p in r.points if p.tag == "quality")
    assert "lossmaking" in quality.text.lower()
