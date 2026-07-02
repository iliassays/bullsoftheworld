"""Sponsor falling-streak detector — pure unit tests on fabricated snapshots."""

from __future__ import annotations

import datetime as dt

from bulls.core.models import ShareholdingSnapshot
from ingestion.signals.ownership import detect_sponsor_streak, render


def _snap(month: int, sponsor: float | None) -> ShareholdingSnapshot:
    return ShareholdingSnapshot(
        market="DSE",
        code="BEXIMCO",
        as_of_date=dt.date(2026, month, 30),
        sponsor_director=sponsor,
    )


def _desc(*sponsors: float | None) -> list[ShareholdingSnapshot]:
    """Newest first, like the runner's query. First value = latest disclosure."""
    return [_snap(7 - i, s) for i, s in enumerate(sponsors)]


def test_three_falling_disclosures_fire() -> None:
    sig = detect_sponsor_streak(_desc(60.3, 61.2, 62.1, 63.4))
    assert sig is not None
    assert sig.event_type == "sponsor_falling_streak"
    assert sig.payload["runs"] == 3
    assert sig.payload["drop"] == 3.1
    assert sig.payload["now"] == 60.3 and sig.payload["prev"] == 63.4


def test_streak_broken_by_a_rise_does_not_fire() -> None:
    assert detect_sponsor_streak(_desc(60.3, 61.2, 60.9, 63.4)) is None


def test_small_cumulative_drop_does_not_fire() -> None:
    # three declines but only 0.6 pp total — below the 1.0 pp materiality floor
    assert detect_sponsor_streak(_desc(62.8, 63.0, 63.2, 63.4)) is None


def test_missing_data_does_not_fire() -> None:
    assert detect_sponsor_streak(_desc(60.3, None, 62.1, 63.4)) is None
    assert detect_sponsor_streak(_desc(60.3, 61.2)) is None


def test_streak_renders_in_both_languages() -> None:
    sig = detect_sponsor_streak(_desc(60.3, 61.2, 62.1, 63.4))
    assert sig is not None
    en = render(sig, "BEXIMCO", "en")
    bn = render(sig, "BEXIMCO", "bn")
    assert "3 disclosures in a row" in en and "63.4% → 60.3%" in en
    assert "BEXIMCO" in bn and "ডিসক্লোজারে কমেছে" in bn
