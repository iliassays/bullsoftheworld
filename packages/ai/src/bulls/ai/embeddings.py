"""Embedding providers for retrieval.

The default hash provider is deterministic and has no service dependency, so small production
servers can run the pgvector pipeline without Ollama. The Ollama provider is an optional semantic
backend for environments where that service is deliberately installed.
"""

from __future__ import annotations

import hashlib
import math
import re

import httpx

from bulls.core.config import get_settings
from bulls.core.models.knowledge import EMBEDDING_DIM

_TOKEN_RE = re.compile(r"[\w$]+", re.UNICODE)


def embedding_model_name() -> str:
    s = get_settings()
    if s.ai_embedding_provider == "ollama":
        return f"ollama:{s.ai_embedding_model}"
    return f"hash:{EMBEDDING_DIM}"


async def embed_text(text: str) -> list[float]:
    s = get_settings()
    if s.ai_embedding_provider == "ollama":
        return await _ollama_embedding(text)
    if s.ai_embedding_provider == "hash":
        return _hash_embedding(text)
    raise ValueError(
        f"Unknown AI_EMBEDDING_PROVIDER {s.ai_embedding_provider!r} "
        "(use 'hash' or 'ollama')"
    )


async def _ollama_embedding(text: str) -> list[float]:
    s = get_settings()
    payload = {"model": s.ai_embedding_model, "prompt": text}
    async with httpx.AsyncClient(base_url=s.ollama_base_url, timeout=60) as client:
        resp = await client.post("/api/embeddings", json=payload)
        resp.raise_for_status()
        embedding = resp.json()["embedding"]
    if len(embedding) != EMBEDDING_DIM:
        raise ValueError(
            f"Embedding dimension mismatch for {s.ai_embedding_model!r}: "
            f"got {len(embedding)}, expected {EMBEDDING_DIM}"
        )
    return [float(x) for x in embedding]


def _hash_embedding(text: str) -> list[float]:
    vec = [0.0] * EMBEDDING_DIM
    for token in _TOKEN_RE.findall(text.lower()):
        h = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "big") % EMBEDDING_DIM
        sign = 1.0 if h[4] & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]
