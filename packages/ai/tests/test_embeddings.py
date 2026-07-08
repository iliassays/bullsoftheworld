"""Embedding provider invariants."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bulls.ai import embeddings
from bulls.ai.embeddings import _fastembed_embedding, _hash_embedding, _validate_dim
from bulls.core.models.knowledge import EMBEDDING_DIM


def test_hash_embedding_dimension_and_determinism():
    a = _hash_embedding("credit rating downgrade risk")
    b = _hash_embedding("credit rating downgrade risk")
    c = _hash_embedding("cash dividend record date")

    assert len(a) == EMBEDDING_DIM
    assert a == b
    assert a != c
    assert sum(x * x for x in a) == pytest.approx(1.0)


def test_embedding_dimension_validation_rejects_wrong_model_width():
    with pytest.raises(ValueError, match="Embedding dimension mismatch"):
        _validate_dim([0.0, 1.0], "too-small")


def test_fastembed_provider_validates_configured_dimension(monkeypatch):
    class FakeFastEmbed:
        def embed(self, texts):
            assert list(texts) == ["semantic DSE disclosure"]
            yield [1.0] + [0.0] * (EMBEDDING_DIM - 1)

    monkeypatch.setattr(
        embeddings,
        "get_settings",
        lambda: SimpleNamespace(
            ai_embedding_model="BAAI/bge-base-en-v1.5",
            ai_embedding_cache_dir=".cache/fastembed",
        ),
    )
    monkeypatch.setattr(embeddings, "_fastembed_model", lambda _model, _cache: FakeFastEmbed())

    assert _fastembed_embedding("semantic DSE disclosure") == [1.0] + [0.0] * (
        EMBEDDING_DIM - 1
    )
