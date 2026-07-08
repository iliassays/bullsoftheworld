"""Embedding provider invariants."""

from __future__ import annotations

import pytest

from bulls.ai.embeddings import _hash_embedding, _validate_dim
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
