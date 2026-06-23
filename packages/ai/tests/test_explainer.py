"""Tests for the technicals explainer.

The renderer is pure (always runs). The live check is opt-in and asserts the explanation passes
the no-advice compliance gate:  RUN_LIVE_EVAL=1 uv run pytest -k live_explainer
"""

from __future__ import annotations

import os

import pytest

from bulls.ai.compliance import contains_advice
from bulls.ai.tasks.explainer import TechnicalsFacts, _render, explain_technicals

FACTS = TechnicalsFacts(
    code="GP",
    name="Grameenphone",
    as_of_date="2026-06-22",
    last_close=254.1,
    above_sma_50=True,
    above_sma_200=False,
    rsi_14=68.7,
    nearest_support=250.5,
    nearest_resistance=257.0,
    week52_high=328.0,
    week52_low=237.4,
    pct_from_52w_high=-22.5,
    relative_volume=1.83,
)


def test_render_includes_only_given_facts():
    text = _render(FACTS)
    assert "254.1" in text and "RSI(14): 69" in text
    assert "support" in text.lower() and "resistance" in text.lower()
    # the renderer must not invent a recommendation
    assert not contains_advice(text).is_advice


@pytest.mark.skipif(not os.getenv("RUN_LIVE_EVAL"), reason="set RUN_LIVE_EVAL=1 for live explainer")
@pytest.mark.asyncio
async def test_live_explainer_is_advice_free():
    explanation = await explain_technicals(FACTS)
    assert explanation and len(explanation) > 20
    # the gate guarantees this, but assert it explicitly as the feature's contract
    assert not contains_advice(explanation).is_advice
