from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from bulls.ai.retrieval import _rerank_score, _retrieval_statement


def test_retrieval_statement_scopes_market_tenant_model_and_code() -> None:
    stmt = _retrieval_statement(
        [0.0] * 768,
        model="fastembed:test:768",
        market="US",
        tenant_id="bullsofwallst",
        code="AAPL",
        limit=24,
    )
    sql = str(stmt.compile(dialect=postgresql.dialect()))

    assert "knowledge_chunks.market" in sql
    assert "knowledge_chunks.embedding_model" in sql
    assert "knowledge_chunks.tenant_id IS NULL" in sql
    assert "knowledge_chunks.tenant_id =" in sql
    assert "knowledge_chunks.code" in sql
    assert "LIMIT" in sql


def test_rerank_rewards_reliable_recent_sources_without_exceeding_semantics() -> None:
    today = dt.datetime.now(dt.UTC).date()
    official = SimpleNamespace(reliability="official", source_date=today)
    crowd = SimpleNamespace(reliability="crowd", source_date=today - dt.timedelta(days=365))

    assert _rerank_score(official, 0.3) > _rerank_score(crowd, 0.3)
