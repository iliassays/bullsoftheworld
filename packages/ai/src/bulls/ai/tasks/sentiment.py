"""Sentiment auto-tagging — the FIRST AI feature (build step 4).

Classifies a post (Bangla or English) as bull / bear / neutral. Ship it WITH an eval set
(see ../evals) so we can measure accuracy, not vibe-check it. Uses structured output.

STATUS: STUB.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SentimentResult(BaseModel):
    label: Literal["bull", "bear", "neutral"]
    confidence: float


async def classify_sentiment(text: str) -> SentimentResult:
    raise NotImplementedError("step 4: Claude structured-output classification + eval harness")
