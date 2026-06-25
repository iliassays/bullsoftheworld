"""Unit tests for the levels render templates.

Pure functions over LevelsInsight — no DB needed, so these always run. They lock in the rule
that an absent support/resistance is stated honestly and NEVER back-filled with a fabricated
number (real money rides on these cards).
"""

from __future__ import annotations

import pytest

from api.routers.levels import _live_bn, _live_en, _relation, _render_bn, _render_en
from bulls.analytics import LevelsInsight


def _insight(**overrides) -> LevelsInsight:
    base = dict(last_close=100.0, pa_direction="flat", pa_sessions=5)
    base.update(overrides)
    return LevelsInsight(**base)


def test_no_levels_states_absence_without_fabricating():
    # Price at an all-time high: no swing pivot above the close → no resistance, no support.
    i = _insight(resistance=None, support=None, rsi=None)
    for render in (_render_en, _render_bn):
        lines = render("GP", i)
        joined = " ".join(lines)
        # Honest absence is shown, and the misleading "levels to watch" footer is gone.
        assert "Levels and concepts to watch" not in joined
        assert "দেখার মতো লেভেল ও ধারণা" not in joined
        assert ("Not enough confirmed price history" in joined) or (
            "যথেষ্ট নিশ্চিত প্রাইস ডেটা নেই" in joined
        )
        # No fabricated level number: a real support/resistance line always carries a ৳ price.
        assert "৳" not in joined
        # Last line is still the no-advice disclaimer (regulatory line must always hold).
        assert "advice" in lines[-1].lower() or "পরামর্শ" in lines[-1]


def test_with_levels_keeps_standard_footer():
    i = _insight(resistance=110.0, support=95.0, volume_confirms=True, rsi=55.0, rsi_zone="neutral")
    en = _render_en("GP", i)
    assert any("Resistance" in line for line in en)
    assert any("Support" in line for line in en)
    assert en[-1] == "Levels and concepts to watch — not predictions or advice."

    bn = _render_bn("GP", i)
    assert any("রেজিস্ট্যান্স" in line for line in bn)
    assert bn[-1] == "দেখার মতো লেভেল ও ধারণা — কোনো ভবিষ্যদ্বাণী বা পরামর্শ নয়।"


@pytest.mark.parametrize("live", [_live_en, _live_bn])
def test_live_line_never_crashes_on_one_sided_levels(live):
    # Regression: a one-sided level (support set, resistance None — or vice versa) must not raise.
    # The live line is built only for the selected relation; the missing side is never formatted.
    price, support, resistance = 100.0, 95.0, None
    rel = _relation(price, support, resistance)
    assert live(price, rel, support, resistance)  # no TypeError on None resistance

    price2, support2, resistance2 = 100.0, None, 110.0
    rel2 = _relation(price2, support2, resistance2)
    assert live(price2, rel2, support2, resistance2)  # no TypeError on None support

    # No levels at all → falls through to the plain price line, still no crash.
    assert live(100.0, _relation(100.0, None, None), None, None)
