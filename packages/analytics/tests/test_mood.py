"""Dhaka Mood Index — deterministic fear/greed composite. Descriptive, omit-over-mislead, bilingual."""

from __future__ import annotations

from bulls.analytics.mood import build_mood

# A calm, low-vol DSEX series (tiny alternating wiggle) so the volatility sub-index is computable.
_CALM = [100 + (i % 2) * 0.1 for i in range(120)]


def test_extreme_greed():
    m = build_mood(
        as_of_date="2026-06-30",
        advancers=300,
        decliners=20,
        pct_above_200dma=0.9,
        n_near_52w_high=40,
        n_near_52w_low=2,
        dsex_closes=_CALM,
    )
    assert m.score is not None and m.score >= 75
    assert m.band == "extreme_greed"
    assert "greedy" in m.caption.lower()


def test_extreme_fear():
    m = build_mood(
        as_of_date="2026-06-30",
        advancers=15,
        decliners=320,
        pct_above_200dma=0.08,
        n_near_52w_high=1,
        n_near_52w_low=44,
        dsex_closes=_CALM,
    )
    assert m.score is not None and m.score <= 25
    assert m.band == "extreme_fear"
    assert "fearful" in m.caption.lower()


def test_neutral_band():
    m = build_mood(
        as_of_date="2026-06-30",
        advancers=120,
        decliners=120,
        pct_above_200dma=0.5,
        n_near_52w_high=10,
        n_near_52w_low=10,
        dsex_closes=_CALM,
    )
    assert m.band == "neutral"
    assert 45 <= (m.score or 0) < 56


def test_omit_over_mislead_too_few_components():
    # Only breadth is computable → below the 2-component floor → score stays None, never faked.
    m = build_mood(as_of_date="2026-06-30", advancers=200, decliners=50)
    assert m.score is None
    assert m.band == "unknown"
    assert {c.key for c in m.components} == {"breadth"}


def test_components_omitted_individually():
    # No 52w highs/lows and no DSEX history → those two sub-indices are dropped, others remain.
    m = build_mood(
        as_of_date="2026-06-30",
        advancers=200,
        decliners=100,
        pct_above_200dma=0.6,
    )
    keys = {c.key for c in m.components}
    assert keys == {"breadth", "strength"}
    assert m.score is not None  # two components clears the floor


def test_turnover_is_context_not_scored():
    m = build_mood(
        as_of_date="2026-06-30",
        advancers=200,
        decliners=100,
        pct_above_200dma=0.6,
        turnover_vs_20d=1.3,
    )
    assert all(c.key != "turnover" for c in m.components)
    assert any("1.3" in c for c in m.context)


def test_bilingual_bn():
    m = build_mood(
        as_of_date="2026-06-30",
        locale="bn",
        advancers=300,
        decliners=20,
        pct_above_200dma=0.9,
        n_near_52w_high=40,
        n_near_52w_low=2,
        dsex_closes=_CALM,
    )
    assert m.label == "চরম লোভ"
    assert "লোভ" in m.caption
    assert "সুপারিশ" in m.disclaimer  # "not a recommendation"
