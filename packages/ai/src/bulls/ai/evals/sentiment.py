"""Sentiment eval scorer.

`score()` is a pure function (no API) so it's unit-testable. `run_eval()` calls the live
classifier over the dataset and returns the score report.
"""

from __future__ import annotations

import asyncio
from collections import Counter

from pydantic import BaseModel

from bulls.ai.evals.dataset import SENTIMENT_EVAL_SET, Example
from bulls.ai.tasks.sentiment import classify_sentiment

LABELS = ("bull", "bear", "neutral")


class Mistake(BaseModel):
    text: str
    expected: str
    predicted: str


class EvalReport(BaseModel):
    total: int
    correct: int
    accuracy: float
    per_label_accuracy: dict[str, float]
    confusion: dict[str, dict[str, int]]  # expected -> predicted -> count
    mistakes: list[Mistake]


def score(examples: list[Example], predicted: list[str]) -> EvalReport:
    """Pure scorer: compare gold labels to predictions. No network."""
    if len(examples) != len(predicted):
        raise ValueError("examples and predictions must be the same length")

    confusion = {e: dict.fromkeys(LABELS, 0) for e in LABELS}
    per_label_total: Counter[str] = Counter()
    per_label_correct: Counter[str] = Counter()
    mistakes: list[Mistake] = []
    correct = 0

    for ex, pred in zip(examples, predicted, strict=True):
        per_label_total[ex.label] += 1
        if pred in confusion[ex.label]:
            confusion[ex.label][pred] += 1
        if pred == ex.label:
            correct += 1
            per_label_correct[ex.label] += 1
        else:
            mistakes.append(Mistake(text=ex.text, expected=ex.label, predicted=pred))

    per_label_accuracy = {
        label: round(per_label_correct[label] / per_label_total[label], 3)
        for label in LABELS
        if per_label_total[label]
    }
    return EvalReport(
        total=len(examples),
        correct=correct,
        accuracy=round(correct / len(examples), 3) if examples else 0.0,
        per_label_accuracy=per_label_accuracy,
        confusion=confusion,
        mistakes=mistakes,
    )


async def run_eval(*, concurrency: int = 5) -> EvalReport:
    """Run the live classifier (configured provider) over the eval set and score it."""
    sem = asyncio.Semaphore(concurrency)

    async def predict(ex: Example) -> str:
        async with sem:
            result = await classify_sentiment(ex.text)
            return result.label

    predictions = await asyncio.gather(*(predict(ex) for ex in SENTIMENT_EVAL_SET))
    return score(SENTIMENT_EVAL_SET, list(predictions))
