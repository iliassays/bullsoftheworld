"""Tests for the symbol digest.

crowd_mood is pure (always runs). The live grounding check is opt-in:
    RUN_LIVE_EVAL=1 uv run pytest -k live_digest
"""

from __future__ import annotations

import os

import pytest

from bulls.ai.tasks.digest import SymbolFacts, crowd_mood, summarize_symbol


def test_crowd_mood():
    assert crowd_mood(0, 0, 0) == "quiet"
    assert crowd_mood(8, 1, 1) == "bullish"
    assert crowd_mood(1, 8, 1) == "bearish"
    assert crowd_mood(3, 3, 4) == "mixed"
    assert crowd_mood(5, 0, 5) == "bullish"  # lean 0.5


@pytest.mark.skipif(not os.getenv("RUN_LIVE_EVAL"), reason="set RUN_LIVE_EVAL=1 for live digest")
@pytest.mark.asyncio
async def test_live_digest_is_grounded():
    facts = SymbolFacts(
        code="GP",
        name="Grameenphone",
        last_price=254.1,
        change_pct_1d=-1.13,
        change_pct_5d=2.4,
        last_volume=283730,
        avg_volume_5d=200000,
        bull_posts=5,
        bear_posts=1,
        neutral_posts=0,
        sample_posts=["$GP breaking out, buying more"],
    )
    summary = await summarize_symbol(facts)
    assert summary and len(summary) > 10
    # grounded: must not invent a price the facts never mention
    assert "999" not in summary
