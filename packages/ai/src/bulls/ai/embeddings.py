"""Embedding providers for retrieval.

The production-quality free path is ``fastembed``: it runs a local ONNX sentence embedding model
inside the worker/backfill process and stores 768-wide vectors in pgvector. ``hash`` stays as a
deterministic no-dependency fallback for tiny environments and tests. Hosted and Ollama providers
remain opt-in only.
"""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache
from typing import Any

import httpx

from bulls.core.config import get_settings
from bulls.core.models.knowledge import EMBEDDING_DIM

_TOKEN_RE = re.compile(r"[\w$]+", re.UNICODE)


def embedding_model_name() -> str:
    s = get_settings()
    if s.ai_embedding_provider == "fastembed":
        return f"fastembed:{s.ai_embedding_model}:{s.ai_embedding_dimensions}"
    if s.ai_embedding_provider == "openai":
        return f"openai:{s.ai_embedding_model}:{s.ai_embedding_dimensions}"
    if s.ai_embedding_provider == "ollama":
        return f"ollama:{s.ai_embedding_model}"
    return f"hash:{EMBEDDING_DIM}"


async def embed_text(text: str) -> list[float]:
    """Backward-compatible generic embedding; new retrieval code uses role-specific helpers."""
    s = get_settings()
    if s.ai_embedding_provider == "fastembed":
        return _fastembed_embedding(text)
    if s.ai_embedding_provider == "openai":
        return await _openai_embedding(text)
    if s.ai_embedding_provider == "ollama":
        return await _ollama_embedding(text)
    if s.ai_embedding_provider == "hash":
        return _hash_embedding(text)
    raise ValueError(
        f"Unknown AI_EMBEDDING_PROVIDER {s.ai_embedding_provider!r} "
        "(use 'fastembed', 'hash', 'openai', or 'ollama')"
    )


async def embed_query_text(text: str) -> list[float]:
    if get_settings().ai_embedding_provider == "fastembed":
        return _fastembed_embedding(text, role="query")
    return await embed_text(text)


async def embed_document_text(text: str) -> list[float]:
    if get_settings().ai_embedding_provider == "fastembed":
        return _fastembed_embedding(text, role="passage")
    return await embed_text(text)


@lru_cache(maxsize=2)
def _fastembed_model(model_name: str, cache_dir: str) -> Any:
    try:
        from fastembed import TextEmbedding
    except ImportError as e:  # pragma: no cover - exercised only in stripped deployments
        raise RuntimeError(
            "AI_EMBEDDING_PROVIDER=fastembed requires the fastembed package. "
            "Run `uv sync` after updating dependencies, or switch AI_EMBEDDING_PROVIDER=hash."
        ) from e
    return TextEmbedding(model_name=model_name, cache_dir=cache_dir)


def _fastembed_embedding(text: str, *, role: str = "document") -> list[float]:
    s = get_settings()
    model = _fastembed_model(s.ai_embedding_model, s.ai_embedding_cache_dir)
    if role == "query":
        embedding = next(iter(model.query_embed(text or " ")))
    elif role == "passage":
        embedding = next(iter(model.passage_embed([text or " "])))
    else:
        embedding = next(iter(model.embed([text or " "])))
    if hasattr(embedding, "tolist"):
        embedding = embedding.tolist()
    return _validate_dim([float(x) for x in embedding], s.ai_embedding_model)


async def _openai_embedding(text: str) -> list[float]:
    s = get_settings()
    if not s.ai_embedding_api_key:
        raise ValueError("AI_EMBEDDING_API_KEY is required when AI_EMBEDDING_PROVIDER=openai")
    payload = {
        "model": s.ai_embedding_model,
        "input": text,
        "dimensions": s.ai_embedding_dimensions,
    }
    async with httpx.AsyncClient(base_url=s.ai_embedding_api_base_url, timeout=30) as client:
        resp = await client.post(
            "/embeddings",
            headers={"Authorization": f"Bearer {s.ai_embedding_api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        embedding = resp.json()["data"][0]["embedding"]
    return _validate_dim([float(x) for x in embedding], s.ai_embedding_model)


async def _ollama_embedding(text: str) -> list[float]:
    s = get_settings()
    payload = {"model": s.ai_embedding_model, "prompt": text}
    async with httpx.AsyncClient(base_url=s.ollama_base_url, timeout=60) as client:
        resp = await client.post("/api/embeddings", json=payload)
        resp.raise_for_status()
        embedding = resp.json()["embedding"]
    return _validate_dim([float(x) for x in embedding], s.ai_embedding_model)


def _validate_dim(embedding: list[float], model: str) -> list[float]:
    if len(embedding) != EMBEDDING_DIM:
        raise ValueError(
            f"Embedding dimension mismatch for {model!r}: "
            f"got {len(embedding)}, expected {EMBEDDING_DIM}"
        )
    return embedding


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
