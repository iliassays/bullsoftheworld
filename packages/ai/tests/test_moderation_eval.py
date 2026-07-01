"""Tests for the L4 safety/relevance eval harness.

The scorer is pure (no network) and always runs. The live accuracy run is opt-in and needs a model:
    uv run python -m bulls.ai.evals.run_moderation   (or -k live_safety with a provider configured)
"""

from __future__ import annotations

import os

import pytest

from bulls.ai.evals.moderation import SAFETY_EVAL_SET, VERDICTS, SafetyExample, run_eval, score


def test_dataset_covers_all_verdicts():
    assert SAFETY_EVAL_SET, "eval set is empty"
    assert all(ex.expected in VERDICTS for ex in SAFETY_EVAL_SET)
    assert {ex.expected for ex in SAFETY_EVAL_SET} == set(VERDICTS)  # all classes represented


def test_score_perfect():
    exs = [
        SafetyExample(text="a", expected="ok"),
        SafetyExample(text="b", expected="inappropriate"),
    ]
    r = score(exs, ["ok", "inappropriate"])
    assert r.accuracy == 1.0
    assert r.false_flag_rate == 0.0
    assert r.inappropriate_recall == 1.0


def test_score_false_flag_and_recall():
    exs = [
        SafetyExample(text="ok1", expected="ok"),
        SafetyExample(text="ok2", expected="ok"),
        SafetyExample(text="bad", expected="inappropriate"),
    ]
    preds = ["ok", "off_topic", "ok"]  # one ok wrongly flagged; the inappropriate missed
    r = score(exs, preds)
    assert r.false_flag_rate == 0.5  # 1 of 2 ok posts flagged
    assert r.inappropriate_recall == 0.0  # missed the one inappropriate
    assert len(r.mistakes) == 2


@pytest.mark.skipif(not os.getenv("LIVE_AI"), reason="set LIVE_AI=1 with a provider configured")
@pytest.mark.asyncio
async def test_live_safety_low_false_flag():
    r = await run_eval()
    # The bar that matters: don't over-flag normal market talk.
    assert r.false_flag_rate <= 0.2, r.mistakes
