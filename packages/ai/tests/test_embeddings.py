"""Embedding provider invariants."""

from __future__ import annotations

import pytest

from bulls.ai.embeddings import _hash_embedding
from bulls.core.models.knowledge import EMBEDDING_DIM


def test_hash_embedding_dimension_and_determinism():
    a = _hash_embedding("credit rating downgrade risk")
    b = _hash_embedding("credit rating downgrade risk")
    c = _hash_embedding("cash dividend record date")

    assert len(a) == EMBEDDING_DIM
    assert a == b
    assert a != c
    assert sum(x * x for x in a) == pytest.approx(1.0)
