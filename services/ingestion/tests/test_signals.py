"""Unit tests for levels-agent detection + note rendering (pure, always run)."""

from __future__ import annotations

import datetime as dt

from bulls.analytics.engine import AnalyticsResult
from ingestion.signals.levels import detect, render


def _r(**kw) -> AnalyticsResult:
    base = dict(
        market="DSE",
        code="GP",
        as_of_date=dt.date(2026, 6, 24),
        bars_used=300,
        last_close=100.0,
        last_volume=1000,
    )
    base.update(kw)
    return AnalyticsResult(**base)


def test_no_prior_emits_nothing():
    assert detect(None, _r()) == []


def test_new_52w_high():
    sigs = detect(_r(week52_high=100), _r(last_close=105))
    assert [s.event_type for s in sigs] == ["new_52w_high"]


def test_breakout_needs_volume():
    prev = _r(nearest_resistance=100)
    assert any(
        s.event_type == "breakout" for s in detect(prev, _r(last_close=101, relative_volume=1.5))
    )
    # same break, weak volume → not confirmed
    assert not any(
        s.event_type == "breakout" for s in detect(prev, _r(last_close=101, relative_volume=0.8))
    )


def test_ma200_cross_and_rsi():
    up = detect(_r(above_sma_200=False), _r(above_sma_200=True))
    assert any(s.event_type == "ma200_cross_up" for s in up)
    ob = detect(_r(rsi_14=68), _r(rsi_14=72))
    assert any(s.event_type == "rsi_overbought" for s in ob)


def test_render_is_descriptive_bilingual_no_advice():
    sig = detect(_r(week52_high=100), _r(last_close=105))[0]
    en = render(sig, "GP", "en")
    bn = render(sig, "GP", "bn")
    assert "GP" in en and "৳105" in en
    assert "52-week" in en and "not a recommendation" in en
    assert "৫২-সপ্তাহ" in bn and "পরামর্শ নয়" in bn
    for txt in (en, bn):
        assert "buy" not in txt.lower() and "sell" not in txt.lower()
