"""RAG retrieval over pgvector.

Exact facts stay in normal tables. This module indexes and retrieves messy text evidence so stock
research answers can cite relevant source material even when the user's question uses different
wording than the source.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.ai.embeddings import embed_text, embedding_model_name
from bulls.core.models import Announcement, Cashtag, KnowledgeChunk, Post, SignalEvent

Reliability = Literal["official", "market", "system", "crowd"]

_CHUNK_CHARS = 1200
_CHUNK_OVERLAP = 160
_FETCH_MULTIPLIER = 4


class RetrievedChunk(BaseModel):
    source_type: str
    source_id: str
    title: str
    text: str
    score: float
    reliability: Reliability
    source_date: str | None = None
    code: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ChunkInput:
    market: str
    code: str | None
    source_type: str
    source_id: str
    title: str
    text: str
    reliability: Reliability
    source_date: dt.date | None = None
    tenant_id: str | None = None
    metadata: dict[str, Any] | None = None


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _chunks(text: str) -> list[str]:
    clean = " ".join(text.split())
    if not clean:
        return []
    if len(clean) <= _CHUNK_CHARS:
        return [clean]
    out: list[str] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + _CHUNK_CHARS)
        out.append(clean[start:end])
        if end == len(clean):
            break
        start = max(0, end - _CHUNK_OVERLAP)
    return out


async def upsert_source_chunks(session, source: ChunkInput) -> int:
    """Embed and upsert chunks for one source. Returns number of chunks written."""
    written = 0
    model = embedding_model_name()
    for idx, text in enumerate(_chunks(source.text)):
        embedding = await embed_text(f"{source.title}\n\n{text}")
        row = {
            "tenant_id": source.tenant_id,
            "market": source.market,
            "code": source.code,
            "source_type": source.source_type,
            "source_id": source.source_id,
            "chunk_index": idx,
            "source_date": source.source_date,
            "title": source.title,
            "text": text,
            "reliability": source.reliability,
            "metadata": source.metadata,
            "content_hash": _content_hash(text),
            "embedding_model": model,
            "embedding": embedding,
        }
        stmt = (
            pg_insert(KnowledgeChunk.__table__)
            .values(row)
            .on_conflict_do_update(
                constraint="uq_knowledge_chunk_source",
                set_={
                    "title": row["title"],
                    "text": row["text"],
                    "source_date": row["source_date"],
                    "reliability": row["reliability"],
                    "metadata": row["metadata"],
                    "content_hash": row["content_hash"],
                    "embedding_model": row["embedding_model"],
                    "embedding": row["embedding"],
                },
            )
        )
        await session.execute(stmt)
        written += 1
    return written


async def index_announcement(session, announcement_id: int) -> int:
    a = await session.get(Announcement, announcement_id)
    if a is None:
        return 0
    text = "\n\n".join(x for x in (a.headline, a.body or "") if x)
    return await upsert_source_chunks(
        session,
        ChunkInput(
            market=a.market,
            code=a.code,
            source_type="announcement",
            source_id=str(a.id),
            title=f"{a.category.replace('_', ' ').title()}: {a.headline}",
            text=text,
            reliability="official",
            source_date=a.published_at,
            metadata={"category": a.category, "strength": a.strength, "details": a.details},
        ),
    )


async def index_post(session, post_id: int) -> int:
    post = await session.get(Post, post_id)
    if post is None or post.moderation_status != "published":
        return 0
    rows = list(await session.scalars(select(Cashtag).where(Cashtag.post_id == post_id)))
    written = 0
    for tag in rows:
        written += await upsert_source_chunks(
            session,
            ChunkInput(
                tenant_id=post.tenant_id,
                market=tag.market,
                code=tag.code,
                source_type="post",
                source_id=str(post.id),
                title=f"Platform post ({post.sentiment or 'neutral'})",
                text=post.body,
                reliability="crowd",
                source_date=post.created_at.date(),
                metadata={"sentiment": post.sentiment, "kind": post.kind},
            ),
        )
    return written


async def index_signal_event(session, signal_event_id: int) -> int:
    s = await session.get(SignalEvent, signal_event_id)
    if s is None:
        return 0
    text = f"{s.agent} detected {s.event_type.replace('_', ' ')}. Occurrence: {s.occurrence_key}."
    return await upsert_source_chunks(
        session,
        ChunkInput(
            market=s.market,
            code=s.code,
            source_type="signal",
            source_id=str(s.id),
            title=f"{s.agent}: {s.event_type.replace('_', ' ')}",
            text=text,
            reliability="system",
            source_date=s.as_of_date,
            metadata={"agent": s.agent, "event_type": s.event_type, "post_id": s.post_id},
        ),
    )


async def retrieve(
    session,
    query: str,
    *,
    market: str,
    code: str | None = None,
    k: int = 6,
) -> list[RetrievedChunk]:
    query_embedding = await embed_text(query)
    model = embedding_model_name()
    distance = KnowledgeChunk.embedding.cosine_distance(query_embedding).label("distance")
    stmt = select(KnowledgeChunk, distance).where(
        KnowledgeChunk.market == market,
        KnowledgeChunk.embedding_model == model,
    )
    if code:
        stmt = stmt.where(KnowledgeChunk.code == code)
    stmt = stmt.order_by(distance).limit(k * _FETCH_MULTIPLIER)
    rows = (await session.execute(stmt)).all()
    out: list[RetrievedChunk] = []
    for chunk, dist in rows:
        score = _rerank_score(chunk, float(dist or 0.0))
        out.append(
            RetrievedChunk(
                source_type=chunk.source_type,
                source_id=chunk.source_id,
                title=chunk.title,
                text=chunk.text,
                score=round(score, 4),
                reliability=chunk.reliability,
                source_date=str(chunk.source_date) if chunk.source_date else None,
                code=chunk.code,
                metadata=chunk.metadata_,
            )
        )
    return sorted(out, key=lambda x: x.score, reverse=True)[:k]


def _rerank_score(chunk: KnowledgeChunk, distance: float) -> float:
    semantic = max(0.0, 1.0 - distance)
    reliability = {"official": 0.18, "market": 0.12, "system": 0.10, "crowd": 0.02}.get(
        chunk.reliability, 0.0
    )
    recency = 0.0
    if chunk.source_date:
        age = (dt.datetime.now(dt.UTC).date() - chunk.source_date).days
        if age <= 7:
            recency = 0.12
        elif age <= 30:
            recency = 0.07
        elif age <= 90:
            recency = 0.03
    return round(semantic + reliability + recency, 4)
