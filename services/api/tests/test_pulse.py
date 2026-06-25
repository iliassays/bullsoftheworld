"""Unit tests for the pulse gauge helpers (pure, always run)."""

from __future__ import annotations

from api.routers.pulse import participation_gauge, sentiment_gauge, volume_gauge


def test_sentiment_gauge():
    assert sentiment_gauge(0, 0, 0).score == 50  # no directional posts → neutral
    assert sentiment_gauge(8, 0, 0) == sentiment_gauge(8, 0, 0)
    assert sentiment_gauge(8, 0, 0).score == 100 and sentiment_gauge(8, 0, 0).label == "bullish"
    assert sentiment_gauge(0, 8, 0).score == 0 and sentiment_gauge(0, 8, 0).label == "bearish"
    assert sentiment_gauge(5, 5, 0).score == 50 and sentiment_gauge(5, 5, 0).label == "mixed"


def test_volume_gauge():
    assert volume_gauge(0, None).label == "quiet"
    assert volume_gauge(10, 3.0).label == "high"  # 3x usual chatter
    assert volume_gauge(5, None).label == "normal"


def test_participation_gauge():
    assert participation_gauge(0, 0).label == "quiet"
    assert participation_gauge(8, 10).label == "high"  # many distinct voices
    assert participation_gauge(2, 10).label == "low"  # a few accounts dominate
