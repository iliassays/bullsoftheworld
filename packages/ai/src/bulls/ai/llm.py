"""LLM provider dispatch — the swap point between a free local model and Claude.

`structured_complete()` returns a validated Pydantic object regardless of provider, so feature
code (sentiment, summaries, …) never branches on which model is running. Flip `AI_PROVIDER`.
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel

from bulls.ai.client import default_model, get_client
from bulls.core.config import get_settings


async def structured_complete[T: BaseModel](system: str, user: str, schema: type[T]) -> T:
    """Get a schema-validated structured response from the configured provider."""
    provider = get_settings().ai_provider
    if provider == "ollama":
        return await _ollama(system, user, schema)
    if provider == "claude":
        return await _claude(system, user, schema)
    raise ValueError(f"Unknown AI_PROVIDER {provider!r} (use 'ollama' or 'claude')")


async def _claude[T: BaseModel](system: str, user: str, schema: type[T]) -> T:
    resp = await get_client().messages.parse(
        model=default_model(),
        max_tokens=256,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=schema,
    )
    return resp.parsed_output


async def _ollama[T: BaseModel](system: str, user: str, schema: type[T]) -> T:
    """Call a local Ollama model with structured output (format = JSON schema)."""
    s = get_settings()
    payload = {
        "model": s.ollama_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": schema.model_json_schema(),  # Ollama constrains output to this schema
        "options": {"temperature": 0},
    }
    async with httpx.AsyncClient(base_url=s.ollama_base_url, timeout=120) as client:
        resp = await client.post("/api/chat", json=payload)
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
    return schema.model_validate_json(content)
