"""L4 safety + relevance screen (async, runs in ai_worker — never on a web request).

Second opinion on posts the deterministic layers passed: catches inappropriate content and off-topic
chit-chat that keyword rules miss. Provider-agnostic (local Ollama or Claude via `structured_complete`).
A flag routes the post to the human review queue — it never auto-deletes (over-flagging is the fear).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from bulls.ai.llm import structured_complete
from bulls.ai.prompts.moderation import SAFETY_SYSTEM_V1

Verdict = Literal["ok", "inappropriate", "off_topic"]
SafetyCategory = Literal["none", "hate", "sexual", "harassment", "threat", "spam", "off_topic"]


class SafetyResult(BaseModel):
    verdict: Verdict = "ok"
    category: SafetyCategory = "none"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""


async def screen_post(text: str) -> SafetyResult:
    """Classify one post for safety + relevance via the configured provider."""
    return await structured_complete(SAFETY_SYSTEM_V1, text, SafetyResult)
