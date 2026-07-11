"""Unit tests for levels-agent detection + note rendering (pure, always run)."""

from __future__ import annotations

import datetime as dt

from bulls.analytics.engine import AnalyticsResult
from bulls.core.models import MarketSummary, ShareholdingSnapshot
from ingestion.signals import market as market_wrap
from ingestion.signals import ownership, volume
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


def test_render_uses_market_currency_without_leaking_taka() -> None:
    sig = detect(_r(nearest_support=100), _r(last_close=95))[0]
    us = render(sig, "AAPL", "en", "$")
    assert "$100" in us
    assert "৳" not in us


def _snap(d: dt.date, **kw) -> ShareholdingSnapshot:
    return ShareholdingSnapshot(market="DSE", code="GP", as_of_date=d, **kw)


def test_ownership_detect_thresholds():
    prev = _snap(dt.date(2026, 4, 30), foreign_pct=5.0, institute=10.0, sponsor_director=30.0)
    latest = _snap(dt.date(2026, 5, 31), foreign_pct=6.5, institute=10.5, sponsor_director=30.0)
    ev = {s.event_type for s in ownership.detect(prev, latest)}
    assert "foreign_change" in ev  # +1.5pp ≥ 1.0
    assert "institution_change" not in ev  # +0.5pp < 2.0
    assert "sponsor_change" not in ev  # no change


def test_ownership_render_descriptive_bilingual():
    sig = ownership.detect(
        _snap(dt.date(2026, 4, 30), foreign_pct=5.0),
        _snap(dt.date(2026, 5, 31), foreign_pct=6.5),
    )[0]
    en = ownership.render(sig, "GP", "en")
    bn = ownership.render(sig, "GP", "bn")
    assert "6.5%" in en and "5.0%" in en and "raised" in en and "not advice" in en
    assert "পরামর্শ নয়" in bn
    for txt in (en, bn):
        assert "buy" not in txt.lower() and "sell" not in txt.lower()


def test_volume_detect_threshold_and_floor():
    assert volume.detect(None, 100_000, 1.0, "d") is None  # no volume
    assert volume.detect(300_000, 40_000, 1.0, "d") is None  # below liquidity floor
    assert volume.detect(100_000, 100_000, 1.0, "d") is None  # 1x — normal
    assert volume.detect(300_000, 100_000, 1.0, "d").event_type == "unusual_volume"  # 3x
    # day-fraction: a half-day's volume is judged against expected-by-now
    assert volume.detect(130_000, 100_000, 0.5, "d") is not None  # 2.6x of expected
    assert volume.detect(110_000, 100_000, 0.5, "d") is None  # 2.2x — under


def test_market_render():
    # dsex_change is POINTS (DSE convention): +43.4 points on 5420 = +0.81%.
    s = MarketSummary(
        market="DSE",
        date=dt.date(2026, 6, 25),
        dsex=5420.0,
        dsex_change=43.4,
        total_value_mn=6200.0,
    )
    en = market_wrap.render(s, 180, 95, "en")
    bn = market_wrap.render(s, 180, 95, "bn")
    assert "DSEX 5,420" in en and "+0.81%" in en and "180 advancers" in en and "৳620 Cr" in en
    assert "not advice" in en and "পরামর্শ নয়" in bn
