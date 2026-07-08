"""Source chunks for retrieval-augmented research.

The DB remains the source of truth for exact facts. This table is only an evidence index over messy
text sources (announcements, posts, agent notes, filings later), scoped by market/code so retail
research answers can cite where the explanation came from.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base

EMBEDDING_DIM = 768


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    market: Mapped[str] = mapped_column(String(8), index=True)
    code: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)
    source_type: Mapped[str] = mapped_column(String(24), index=True)
    source_id: Mapped[str] = mapped_column(String(64))
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    source_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    reliability: Mapped[str] = mapped_column(String(16))  # official | market | system | crowd
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    embedding_model: Mapped[str] = mapped_column(String(80))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_id",
            "code",
            "chunk_index",
            name="uq_knowledge_chunk_source",
        ),
    )
