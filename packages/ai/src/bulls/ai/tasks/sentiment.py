"""Sentiment auto-tagging — the FIRST AI feature (build step 4).

Classifies a post (Bangla or English) as bull / bear / neutral via Claude structured output.
Ships WITH an eval set (see ../evals) so accuracy is measured, not vibe-checked.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from bulls.ai.llm import structured_complete
from bulls.ai.prompts.sentiment import SENTIMENT_SYSTEM_V1

Label = Literal["bull", "bear", "neutral"]


class SentimentResult(BaseModel):
    label: Label
    confidence: float = Field(ge=0.0, le=1.0)


async def classify_sentiment(text: str) -> SentimentResult:
    """Classify one post via the configured provider (local Ollama or Claude)."""
    return await structured_complete(SENTIMENT_SYSTEM_V1, text, SentimentResult)
