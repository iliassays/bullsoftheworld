"""RAG retrieval over pgvector (build step 5).

Embeds posts/news and retrieves relevant context for grounded company Q&A. Uses the same Postgres
instance (pgvector extension) — no separate vector DB needed at this scale.

STATUS: STUB.
"""

from __future__ import annotations

from pydantic import BaseModel


class RetrievedChunk(BaseModel):
    source: str
    text: str
    score: float


async def retrieve(query: str, *, market: str, k: int = 6) -> list[RetrievedChunk]:
    raise NotImplementedError("step 5: embed query, pgvector similarity search, return top-k")
