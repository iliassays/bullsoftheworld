"""Translate a post into the reader's language (free local model or Claude)."""

from __future__ import annotations

from pydantic import BaseModel

from bulls.ai.llm import structured_complete
from bulls.ai.prompts.translate import TRANSLATE_SYSTEM_V1


class TranslateOut(BaseModel):
    text: str


async def translate(text: str, *, language: str = "English") -> str:
    system = TRANSLATE_SYSTEM_V1.format(language=language)
    result = await structured_complete(system, text, TranslateOut)
    return result.text.strip()
