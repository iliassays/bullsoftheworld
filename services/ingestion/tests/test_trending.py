"""Unit tests for the daily activity ranking helpers."""

from __future__ import annotations

import numpy as np

from ingestion.trending import _week52_position


def test_week52_position_requires_full_year():
    pct_high, pct_low = _week52_position(np.arange(1, 66, dtype=float), 65.0)

    assert pct_high is None
    assert pct_low is None


def test_week52_position_uses_252_session_window():
    closes = np.array([500.0] + list(range(1, 253)), dtype=float)
    pct_high, pct_low = _week52_position(closes, 252.0)

    assert pct_high == 0.0
    assert pct_low == 25100.0
