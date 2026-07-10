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
from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.ai.embeddings import embed_document_text, embed_query_text, embedding_model_name
from bulls.core.models import (
    Announcement,
    Cashtag,
    InstitutionalHoldingSummary,
    KnowledgeChunk,
    Post,
    SecFiling,
    SecFinancialFact,
    SignalEvent,
)

Reliability = Literal["official", "market", "system", "crowd"]

_CHUNK_CHARS = 1200
_CHUNK_OVERLAP = 160
_FETCH_MULTIPLIER = 4
_MIN_SEMANTIC_SCORE = 0.20


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
    texts = _chunks(source.text)
    for idx, text in enumerate(texts):
        content_hash = _content_hash(f"{source.title}\n\n{text}")
        tenant_scope = (
            KnowledgeChunk.tenant_id.is_(None)
            if source.tenant_id is None
            else KnowledgeChunk.tenant_id == source.tenant_id
        )
        code_scope = (
            KnowledgeChunk.code.is_(None)
            if source.code is None
            else KnowledgeChunk.code == source.code
        )
        existing_hash = await session.scalar(
            select(KnowledgeChunk.content_hash).where(
                tenant_scope,
                KnowledgeChunk.market == source.market,
                code_scope,
                KnowledgeChunk.source_type == source.source_type,
                KnowledgeChunk.source_id == source.source_id,
                KnowledgeChunk.chunk_index == idx,
                KnowledgeChunk.embedding_model == model,
            )
        )
        if existing_hash == content_hash:
            continue
        embedding = await embed_document_text(f"{source.title}\n\n{text}")
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
            "content_hash": content_hash,
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
    # A corrected/shorter source must not leave old tail chunks retrievable.
    tenant_scope = (
        KnowledgeChunk.tenant_id.is_(None)
        if source.tenant_id is None
        else KnowledgeChunk.tenant_id == source.tenant_id
    )
    await session.execute(
        delete(KnowledgeChunk).where(
            tenant_scope,
            KnowledgeChunk.market == source.market,
            KnowledgeChunk.code == source.code,
            KnowledgeChunk.source_type == source.source_type,
            KnowledgeChunk.source_id == source.source_id,
            KnowledgeChunk.embedding_model == model,
            KnowledgeChunk.chunk_index >= len(texts),
        )
    )
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


async def index_sec_filing(session, market: str, code: str, accession_number: str) -> int:
    filing = await session.get(SecFiling, (market, code, accession_number))
    if filing is None:
        return 0
    title = f"SEC {filing.form}: {filing.category.replace('_', ' ').title()}"
    text = ". ".join(
        value
        for value in (
            filing.description,
            f"Filed {filing.filing_date} for report period {filing.report_date}."
            if filing.report_date
            else f"Filed {filing.filing_date}.",
            f"Items: {filing.items}." if filing.items else None,
        )
        if value
    )
    return await upsert_source_chunks(
        session,
        ChunkInput(
            market=filing.market,
            code=filing.code,
            source_type="sec_filing",
            source_id=filing.accession_number,
            title=title,
            text=text,
            reliability="official",
            source_date=filing.filing_date,
            metadata={
                "form": filing.form,
                "category": filing.category,
                "report_date": str(filing.report_date) if filing.report_date else None,
                "url": filing.filing_url,
            },
        ),
    )


async def index_sec_financials(session, market: str, code: str) -> int:
    facts = list(
        await session.scalars(
            select(SecFinancialFact)
            .where(SecFinancialFact.market == market, SecFinancialFact.code == code)
            .order_by(SecFinancialFact.period_end.desc(), SecFinancialFact.filed_at.desc())
        )
    )
    by_period: dict[tuple[dt.date, str], list[SecFinancialFact]] = {}
    for fact in facts:
        by_period.setdefault((fact.period_end, fact.period_type), []).append(fact)
    written = 0
    active_ids: list[str] = []
    for (period_end, period_type), rows in sorted(by_period.items(), reverse=True)[:12]:
        source_id = f"{code}:{period_end}:{period_type}"
        active_ids.append(source_id)
        latest = max(rows, key=lambda row: row.filed_at)
        text = ". ".join(
            f"{row.metric.replace('_', ' ')}: {row.value:,.4g} {row.unit}" for row in rows
        )
        written += await upsert_source_chunks(
            session,
            ChunkInput(
                market=market,
                code=code,
                source_type="sec_financials",
                source_id=source_id,
                title=f"SEC financial facts: {period_type} ending {period_end}",
                text=text,
                reliability="official",
                source_date=latest.filed_at,
                metadata={
                    "period_end": str(period_end),
                    "period_type": period_type,
                    "url": latest.source_url,
                },
            ),
        )
    stale_facts = delete(KnowledgeChunk).where(
        KnowledgeChunk.market == market,
        KnowledgeChunk.code == code,
        KnowledgeChunk.source_type == "sec_financials",
        KnowledgeChunk.embedding_model == embedding_model_name(),
    )
    if active_ids:
        stale_facts = stale_facts.where(KnowledgeChunk.source_id.not_in(active_ids))
    await session.execute(stale_facts)
    await session.execute(
        delete(KnowledgeChunk).where(
            KnowledgeChunk.market == market,
            KnowledgeChunk.code == code,
            KnowledgeChunk.source_type == "sec_filing",
            KnowledgeChunk.embedding_model == embedding_model_name(),
            KnowledgeChunk.source_id.not_in(
                select(SecFiling.accession_number).where(
                    SecFiling.market == market, SecFiling.code == code
                )
            ),
        )
    )
    return written


async def index_institutional_summary(session, market: str, code: str, report_date: dt.date) -> int:
    summary = await session.get(InstitutionalHoldingSummary, (market, code, report_date))
    if summary is None:
        return 0
    change = (
        f"Comparable shares changed {summary.net_change_pct:+.2f}% quarter over quarter. "
        if summary.net_change_pct is not None
        else "A comparable quarter-over-quarter percentage was unavailable. "
    )
    text = (
        f"{summary.managers_count} reporting managers held {summary.total_shares:,} shares "
        f"worth ${summary.total_value_usd:,.0f}. {change}"
        f"New positions {summary.new_positions}; increased {summary.increased_positions}; "
        f"reduced {summary.reduced_positions}; exited {summary.exited_positions}. "
        "Form 13F reports quarter-end long holdings after a filing delay and does not disclose "
        "actual trade dates or prices."
    )
    written = await upsert_source_chunks(
        session,
        ChunkInput(
            market=market,
            code=code,
            source_type="sec_13f",
            source_id=f"{code}:{report_date}",
            title=f"SEC 13F holdings as of {report_date}",
            text=text,
            reliability="official",
            source_date=summary.latest_filing_date,
            metadata={"report_date": str(report_date), "url": summary.source_url},
        ),
    )
    report_dates = list(
        await session.scalars(
            select(InstitutionalHoldingSummary.report_date).where(
                InstitutionalHoldingSummary.market == market,
                InstitutionalHoldingSummary.code == code,
            )
        )
    )
    active_ids = [f"{code}:{date}" for date in report_dates]
    stale = delete(KnowledgeChunk).where(
        KnowledgeChunk.market == market,
        KnowledgeChunk.code == code,
        KnowledgeChunk.source_type == "sec_13f",
        KnowledgeChunk.embedding_model == embedding_model_name(),
    )
    if active_ids:
        stale = stale.where(KnowledgeChunk.source_id.not_in(active_ids))
    await session.execute(stale)
    return written


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
            tenant_id=s.tenant_id,
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
    tenant_id: str,
    code: str | None = None,
    k: int = 6,
) -> list[RetrievedChunk]:
    query_embedding = await embed_query_text(query)
    model = embedding_model_name()
    stmt = _retrieval_statement(
        query_embedding,
        model=model,
        market=market,
        tenant_id=tenant_id,
        code=code,
        limit=k * _FETCH_MULTIPLIER,
    )
    rows = (await session.execute(stmt)).all()
    out: list[RetrievedChunk] = []
    seen_sources: set[tuple[str, str, str | None]] = set()
    for chunk, dist in rows:
        distance = float(dist or 0.0)
        if 1.0 - distance < _MIN_SEMANTIC_SCORE:
            continue
        source_key = (chunk.source_type, chunk.source_id, chunk.code)
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)
        score = _rerank_score(chunk, distance)
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


def _retrieval_statement(
    query_embedding: list[float],
    *,
    model: str,
    market: str,
    tenant_id: str,
    code: str | None,
    limit: int,
):
    distance = KnowledgeChunk.embedding.cosine_distance(query_embedding).label("distance")
    stmt = select(KnowledgeChunk, distance).where(
        KnowledgeChunk.market == market,
        KnowledgeChunk.embedding_model == model,
        # Exchange filings/signals are shared within a market (tenant_id IS NULL); community
        # evidence is private to the tenant that produced it.
        or_(KnowledgeChunk.tenant_id.is_(None), KnowledgeChunk.tenant_id == tenant_id),
    )
    if code:
        stmt = stmt.where(KnowledgeChunk.code == code)
    return stmt.order_by(distance).limit(limit)


def _rerank_score(chunk: KnowledgeChunk, distance: float) -> float:
    semantic = max(0.0, 1.0 - distance)
    reliability = {"official": 0.18, "market": 0.12, "system": 0.10, "crowd": 0.02}.get(
        chunk.reliability, 0.0
    )
    recency = 0.0
    if chunk.source_date:
        age = max(0, (dt.datetime.now(dt.UTC).date() - chunk.source_date).days)
        if age <= 7:
            recency = 0.12
        elif age <= 30:
            recency = 0.07
        elif age <= 90:
            recency = 0.03
    return round(semantic + reliability + recency, 4)
