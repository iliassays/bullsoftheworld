"""Unit tests for the factor-agent detectors — pure, no DB."""

from __future__ import annotations

from types import SimpleNamespace as NS

from ingestion.signals import factors as f

_STRONG = NS(
    mom_12_1=80,
    volatility=40,
    market_cap_mn=5000,
    pe_vs_sector=0.7,
    roe=20,
    pe_ratio=10,
    institute_delta=1.5,
    foreign_delta=1.0,
)


def test_momentum_fires_and_is_descriptive():
    sig = f.detect_momentum(_STRONG, "2026-06")
    assert sig and sig.beat == "momentum"
    note = f.render(sig, "GP", "en")
    assert "+80%" in note and "not advice" in note.lower()
    assert "buy" not in note.lower() and "sell" not in note.lower()


def test_momentum_pump_adds_caution():
    sig = f.detect_momentum(NS(mom_12_1=400, volatility=50, market_cap_mn=200), "2026-06")
    assert "reverse" in f.render(sig, "X", "en").lower()  # parabolic → caution


def test_momentum_skips_weak():
    assert f.detect_momentum(NS(mom_12_1=10, volatility=40, market_cap_mn=5000), "2026-06") is None


def test_quality_needs_cheap_and_strong():
    assert f.detect_quality(_STRONG, "2026-06").beat == "quality"
    # cheap but weak ROE → no
    assert f.detect_quality(NS(pe_vs_sector=0.7, roe=3, pe_ratio=10), "2026-06") is None


def test_smartmoney_needs_both_positive():
    assert f.detect_smartmoney(_STRONG, "2026-06").beat == "smartmoney"
    # institutions up, foreign down → not "broad" accumulation
    assert f.detect_smartmoney(NS(institute_delta=3.0, foreign_delta=-1.0), "2026-06") is None


def test_strength_up_while_market_down():
    assert f.detect_strength(2.5, -0.5, "2026-06-27").beat == "strength"
    assert f.detect_strength(2.5, 1.0, "2026-06-27") is None  # market also up → not standout
    assert "fell 0.5%" in f.render(f.detect_strength(2.5, -0.5, "d"), "GP", "en")


def test_accumulation_fires_on_inflow_flat_price():
    ta = NS(cmf_20=0.25, obv_slope=0.3, sma_50=100.0, last_close=103.0)
    sig = f.detect_accumulation(ta, "2026-06")
    assert sig and sig.beat == "accumulation"
    note = f.render(sig, "GP", "en")
    assert "not advice" in note.lower() and "buy" not in note.lower()


def test_accumulation_skips_when_price_already_ran():
    # money in + OBV up, but price 25% above its base → not "quiet"
    assert (
        f.detect_accumulation(NS(cmf_20=0.3, obv_slope=0.3, sma_50=100.0, last_close=125.0), "m")
        is None
    )
    # money in but OBV not confirming → skip
    assert (
        f.detect_accumulation(NS(cmf_20=0.3, obv_slope=-0.1, sma_50=100.0, last_close=101.0), "m")
        is None
    )


def test_circuit_up_and_down():
    up = f.detect_circuit(10.0, "2026-06-28")
    assert up and up.beat == "circuit" and up.payload["dir"] == "up"
    assert (
        "limit" in f.render(up, "GP", "en").lower() and "advice" in f.render(up, "GP", "en").lower()
    )
    dn = f.detect_circuit(-9.95, "2026-06-28")
    assert dn and dn.payload["dir"] == "down"
    assert f.detect_circuit(8.0, "2026-06-28") is None  # not at the limit
    assert f.detect_circuit(None, "d") is None


def test_breakout_needs_near_high_and_up_today():
    ta = NS(pct_from_52w_high=-0.5)
    assert f.detect_breakout(ta, 2.0, "d").beat == "breakout"  # within 2% of high + up 2%
    assert f.detect_breakout(ta, 0.2, "d") is None  # not up enough today
    assert f.detect_breakout(NS(pct_from_52w_high=-8.0), 3.0, "d") is None  # far from high
    note = f.render(f.detect_breakout(ta, 2.0, "d"), "GP", "en")
    assert "52-week high" in note and "buy" not in note.lower()


def test_bn_locale_renders():
    note = f.render(f.detect_momentum(_STRONG, "2026-06"), "GP", "bn")
    assert "পরামর্শ নয়" in note  # "not advice" in Bangla


def test_index_change_pct_converts_points():
    # The "DSEX fell 19.0%" incident: DSE reports the index change in POINTS. A 19-point
    # fall on a ~5285 index is -0.36%, not -19%.
    from bulls.analytics.indicators import index_change_pct

    pct = index_change_pct(5285.0, -19.0)
    assert pct is not None and round(pct, 2) == -0.36
    assert index_change_pct(None, -19.0) is None
    assert index_change_pct(5285.0, None) is None
    assert index_change_pct(5285.0, -2000.0) is None  # >20%/day → implausible, omit


def test_strength_takes_percent_not_points():
    # -0.36% index day + stock up 2.2% → fires, and the note says the true tiny percent.
    sig = f.detect_strength(2.2, -0.36, "2026-07-02")
    assert sig is not None and sig.payload["idx"] == -0.36
    note = f.render(sig, "UNIONCAP", "en")
    assert "fell 0.36%" in note and "19" not in note
    # A barely-red day (-0.1%) is not "the market fell" — no note.
    assert f.detect_strength(2.2, -0.1, "2026-07-02") is None


def test_market_wrap_renders_percent_from_points():
    from bulls.core.models import MarketSummary
    from ingestion.signals import market as mw

    s = MarketSummary(market="DSE", dsex=5285.0, dsex_change=-19.0, total_value_mn=4200.0)
    note = mw.render(s, 120, 210, "en")
    assert "(-0.36%)" in note and "19.00%" not in note
