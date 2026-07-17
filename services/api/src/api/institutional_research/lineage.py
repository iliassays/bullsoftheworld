"""Immutable evidence persistence for tenant-bound Atlas research runs."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from collections import OrderedDict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.institutional_research.schemas import EvidenceItemOut
from bulls.analytics.research_loop import AutonomousResearchInput, ResearchFact
from bulls.core.models import (
    EvidenceDocument,
    EvidenceSpan,
    ResearchRun,
    ResearchRunEvidence,
)


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _as_utc(value: dt.datetime) -> dt.datetime:
    return value.replace(tzinfo=dt.UTC) if value.tzinfo is None else value.astimezone(dt.UTC)


def _date_at_utc(value: dt.date) -> dt.datetime:
    return dt.datetime.combine(value, dt.time.min, tzinfo=dt.UTC)


def _parse_fact_date(facts: Sequence[ResearchFact]) -> dt.datetime | None:
    for fact in facts:
        if not fact.key.endswith(("_date", "_as_of_date")) or not isinstance(fact.value, str):
            continue
        try:
            return _date_at_utc(dt.date.fromisoformat(fact.value))
        except ValueError:
            continue
    return None


def _source_type(source_id: str, facts: Sequence[ResearchFact]) -> str:
    prefixes = {
        "ticker-analytics:": "ticker_analytics",
        "dse:": "dse_announcement",
        "sec:": "sec_filing",
        "dse-ownership:": "dse_shareholding",
        "sec-13f:": "sec_13f_summary",
        "finra-short-volume:": "finra_short_volume",
    }
    for prefix, source_type in prefixes.items():
        if source_id.startswith(prefix):
            return source_type
    if any(fact.source_kind == "official_evidence" for fact in facts):
        return "official_evidence"
    if any(fact.source_kind == "market_data" for fact in facts):
        return "market_data_calculation"
    return "factor_calculation"


def _source_title(
    *,
    source_type: str,
    code: str,
    facts: Sequence[ResearchFact],
    item: EvidenceItemOut | None,
) -> str:
    if item is not None:
        return item.title
    labels = {
        "ticker_analytics": f"{code} point-in-time analytics snapshot",
        "dse_shareholding": f"{code} reported DSE ownership snapshot",
        "sec_13f_summary": f"{code} SEC Form 13F aggregate snapshot",
        "finra_short_volume": f"{code} FINRA daily short-volume snapshot",
    }
    if source_type in labels:
        return labels[source_type]
    return facts[0].label if len(facts) == 1 else f"{code} registered research facts"


@dataclass(frozen=True, slots=True)
class EvidenceSpanSnapshot:
    ordinal: int
    fact_key: str
    text: str
    text_hash: str
    token_count: int


@dataclass(frozen=True, slots=True)
class EvidenceSourceSnapshot:
    source_type: str
    source_record_id: str
    source_revision: str
    code: str
    title: str
    source_url: str | None
    effective_at: dt.datetime | None
    published_at: dt.datetime | None
    known_at: dt.datetime
    content_hash: str
    purpose: str
    spans: tuple[EvidenceSpanSnapshot, ...]


def build_evidence_source_snapshots(
    payload: AutonomousResearchInput,
    *,
    evidence_items: Iterable[EvidenceItemOut],
) -> tuple[EvidenceSourceSnapshot, ...]:
    """Build a deterministic source ledger from exactly the facts supplied to the reasoner."""

    grouped: OrderedDict[str, list[ResearchFact]] = OrderedDict()
    for fact in payload.facts:
        grouped.setdefault(fact.source_id, []).append(fact)
    official_items = {item.id: item for item in evidence_items}
    cutoff = _as_utc(dt.datetime.fromisoformat(payload.knowledge_cutoff_at.replace("Z", "+00:00")))

    snapshots: list[EvidenceSourceSnapshot] = []
    for source_id, facts in grouped.items():
        item = official_items.get(source_id)
        source_type = _source_type(source_id, facts)
        published_at = _date_at_utc(item.published_at) if item is not None else None
        effective_at = published_at or _parse_fact_date(facts)
        serialized_facts = [fact.model_dump(mode="json") for fact in facts]
        content = _stable_json(
            {
                "market": payload.market,
                "code": payload.code,
                "source_id": source_id,
                "facts": serialized_facts,
            }
        )
        content_hash = _sha256(content)
        spans: list[EvidenceSpanSnapshot] = []
        for ordinal, fact in enumerate(serialized_facts):
            text = _stable_json(fact)
            spans.append(
                EvidenceSpanSnapshot(
                    ordinal=ordinal,
                    fact_key=str(fact["key"]),
                    text=text,
                    text_hash=_sha256(text),
                    token_count=len(text.split()),
                )
            )
        snapshots.append(
            EvidenceSourceSnapshot(
                source_type=source_type,
                source_record_id=f"{payload.code}:{source_id}"[:192],
                source_revision=content_hash,
                code=payload.code,
                title=_source_title(
                    source_type=source_type,
                    code=payload.code,
                    facts=facts,
                    item=item,
                ),
                source_url=item.url if item is not None else None,
                effective_at=effective_at,
                published_at=published_at,
                known_at=cutoff,
                content_hash=content_hash,
                purpose=(
                    "supporting"
                    if any(fact.source_kind == "official_evidence" for fact in facts)
                    else "calculation"
                ),
                spans=tuple(spans),
            )
        )
    return tuple(snapshots)


async def _upsert_document(
    session: AsyncSession,
    *,
    run: ResearchRun,
    source: EvidenceSourceSnapshot,
) -> uuid.UUID:
    identity = {
        "tenant_id": run.tenant_id,
        "market": run.market,
        "source_type": source.source_type,
        "source_record_id": source.source_record_id,
        "source_revision": source.source_revision,
    }
    document_id = uuid.uuid4()
    inserted_id = await session.scalar(
        pg_insert(EvidenceDocument)
        .values(
            id=document_id,
            **identity,
            code=source.code,
            title=source.title,
            source_url=source.source_url,
            effective_at=source.effective_at,
            published_at=source.published_at,
            known_at=source.known_at,
            content_hash=source.content_hash,
            object_key=None,
            media_type="application/vnd.bulls.research-facts+json",
            attributes={
                "lineage_version": "atlas-evidence-v1",
                "known_at_basis": "research_knowledge_cutoff",
            },
        )
        .on_conflict_do_nothing(
            constraint="uq_research_evidence_documents_source_revision"
        )
        .returning(EvidenceDocument.id)
    )
    if inserted_id is not None:
        return inserted_id
    existing_id = await session.scalar(select(EvidenceDocument.id).where(*[
        getattr(EvidenceDocument, key) == value for key, value in identity.items()
    ]))
    if existing_id is None:
        raise RuntimeError("evidence document upsert did not return a tenant-visible row")
    return existing_id


async def _upsert_span(
    session: AsyncSession,
    *,
    run: ResearchRun,
    document_id: uuid.UUID,
    span: EvidenceSpanSnapshot,
) -> uuid.UUID:
    span_id = uuid.uuid4()
    inserted_id = await session.scalar(
        pg_insert(EvidenceSpan)
        .values(
            id=span_id,
            tenant_id=run.tenant_id,
            market=run.market,
            document_id=document_id,
            ordinal=span.ordinal,
            locator={"kind": "registered_fact", "fact_key": span.fact_key},
            text=span.text,
            text_hash=span.text_hash,
            token_count=span.token_count,
        )
        .on_conflict_do_nothing(
            constraint="uq_research_evidence_spans_document_ordinal"
        )
        .returning(EvidenceSpan.id)
    )
    if inserted_id is not None:
        return inserted_id
    existing_id = await session.scalar(
        select(EvidenceSpan.id).where(
            EvidenceSpan.document_id == document_id,
            EvidenceSpan.ordinal == span.ordinal,
            EvidenceSpan.tenant_id == run.tenant_id,
            EvidenceSpan.market == run.market,
        )
    )
    if existing_id is None:
        raise RuntimeError("evidence span upsert did not return a tenant-visible row")
    return existing_id


async def persist_run_evidence(
    session: AsyncSession,
    *,
    run: ResearchRun,
    sources: Sequence[EvidenceSourceSnapshot],
) -> dict[str, uuid.UUID]:
    """Persist the complete input pack and return fact-key to immutable span lineage."""

    fact_spans: dict[str, uuid.UUID] = {}
    for ordinal, source in enumerate(sources):
        document_id = await _upsert_document(session, run=run, source=source)
        session.add(
            ResearchRunEvidence(
                run_id=run.id,
                evidence_document_id=document_id,
                organization_id=run.organization_id,
                tenant_id=run.tenant_id,
                market=run.market,
                ordinal=ordinal,
                disposition="selected",
                purpose=source.purpose,
                retrieval_method="registered_fact_pack",
                retrieval_score=Decimal("1"),
                rerank_score=None,
                rationale="Supplied to the bounded deterministic finance reasoner.",
                attributes={"lineage_version": "atlas-evidence-v1"},
            )
        )
        for span in source.spans:
            if span.fact_key in fact_spans:
                raise RuntimeError(f"duplicate fact lineage for {span.fact_key}")
            fact_spans[span.fact_key] = await _upsert_span(
                session,
                run=run,
                document_id=document_id,
                span=span,
            )
    await session.flush()
    return fact_spans
