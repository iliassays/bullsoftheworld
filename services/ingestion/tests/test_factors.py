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
    assert (
        f.detect_smartmoney(NS(institute_delta=3.0, foreign_delta=-1.0), "2026-06") is None
    )


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
    assert f.detect_accumulation(NS(cmf_20=0.3, obv_slope=0.3, sma_50=100.0, last_close=125.0), "m") is None
    # money in but OBV not confirming → skip
    assert f.detect_accumulation(NS(cmf_20=0.3, obv_slope=-0.1, sma_50=100.0, last_close=101.0), "m") is None


def test_bn_locale_renders():
    note = f.render(f.detect_momentum(_STRONG, "2026-06"), "GP", "bn")
    assert "পরামর্শ নয়" in note  # "not advice" in Bangla
