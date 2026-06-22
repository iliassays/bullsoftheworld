"""Tests for the sentiment eval harness.

The scorer is pure (no network) and always runs. The live accuracy test is opt-in and needs
ANTHROPIC_API_KEY:  ANTHROPIC_API_KEY=... uv run pytest -k live_sentiment
"""

from __future__ import annotations

import os

import pytest

from bulls.ai.evals.dataset import SENTIMENT_EVAL_SET, Example
from bulls.ai.evals.sentiment import LABELS, run_eval, score


def test_dataset_labels_are_valid():
    assert SENTIMENT_EVAL_SET, "eval set is empty"
    assert all(ex.label in LABELS for ex in SENTIMENT_EVAL_SET)
    # cover all three classes so the eval is meaningful
    present = {ex.label for ex in SENTIMENT_EVAL_SET}
    assert present == set(LABELS)


def test_score_perfect():
    exs = [Example(text="a", label="bull"), Example(text="b", label="bear")]
    report = score(exs, ["bull", "bear"])
    assert report.accuracy == 1.0
    assert report.mistakes == []
    assert report.confusion["bull"]["bull"] == 1


def test_score_with_mistakes_and_confusion():
    exs = [
        Example(text="a", label="bull"),
        Example(text="b", label="bull"),
        Example(text="c", label="bear"),
        Example(text="d", label="neutral"),
    ]
    preds = ["bull", "bear", "bear", "bull"]  # 2 right, 2 wrong
    report = score(exs, preds)
    assert report.correct == 2
    assert report.accuracy == 0.5
    assert report.per_label_accuracy["bull"] == 0.5  # 1 of 2 bull right
    assert report.confusion["bull"]["bear"] == 1  # one bull predicted bear
    assert {(m.expected, m.predicted) for m in report.mistakes} == {
        ("bull", "bear"),
        ("neutral", "bull"),
    }


def test_score_length_mismatch_raises():
    with pytest.raises(ValueError, match="same length"):
        score([Example(text="a", label="bull")], [])


@pytest.mark.skipif(
    not os.getenv("RUN_LIVE_EVAL"),
    reason="set RUN_LIVE_EVAL=1 (with Ollama running or a Claude key) for the live eval",
)
@pytest.mark.asyncio
async def test_live_sentiment_accuracy():
    report = await run_eval()
    # a working classifier should clear this low bar comfortably; tune up over time
    assert report.accuracy >= 0.7, report.mistakes
