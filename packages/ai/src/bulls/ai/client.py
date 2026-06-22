"""Thin wrapper around the Claude API.

Centralizes: model selection, cost/usage guards, retries, and (later) response caching in Redis.
Keep prompt text out of here — prompts live in `prompts/` and are versioned.
"""

from __future__ import annotations

from functools import lru_cache

from anthropic import AsyncAnthropic

from bulls.core.config import get_settings


@lru_cache
def get_client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=get_settings().anthropic_api_key)


def default_model() -> str:
    return get_settings().anthropic_model
