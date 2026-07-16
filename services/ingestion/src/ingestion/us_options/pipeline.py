"""Phase A Option Sentiment import pipeline.

The pipeline stores licensed raw bytes and normalized Parquet, then writes a small manifest to
PostgreSQL. It does not publish features or expose customer-facing data.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import os
import stat
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bulls.core.config import Settings, get_settings
from bulls.core.models import (
    ResearchDataEntitlement,
    ResearchDatasetSnapshot,
    SecurityMaster,
)
from bulls.market_data.options.cboe_sentiment import (
    CBOE_OPTION_SENTIMENT_SCHEMA_VERSION,
    MAX_ARCHIVE_BYTES,
    MAX_CSV_BYTES,
    OptionSentimentCompleteness,
    parse_cboe_option_sentiment,
)
from ingestion.us_options.parquet import option_sentiment_parquet
from ingestion.us_options.quality import (
    IDENTITY_VERSION,
    NORMALIZATION_VERSION,
    SecurityAlias,
    normalize_option_sentiment,
)
from ingestion.us_options.storage import ImmutableObjectStore, object_store

TENANT_ID = "bullsofwallst"
MARKET = "US"
DATASET_KEY = "cboe_option_sentiment"
PROVIDER = "Cboe DataShop"
_EASTERN = ZoneInfo("America/New_York")
_SPEC_URL = "https://datashop.cboe.com/Documents/Cboe_OptionSentiment_Specs.pdf"
OptionSentimentDeliveryMode = Literal["historical", "subscription"]


def entitlement_allows_internal_research(
    entitlement: ResearchDataEntitlement,
    *,
    on_date: dt.date,
) -> bool:
    return bool(
        entitlement.status == "approved"
        and entitlement.internal_research_allowed
        and entitlement.retention_allowed
        and (entitlement.valid_from is None or entitlement.valid_from <= on_date)
        and (entitlement.valid_until is None or on_date <= entitlement.valid_until)
    )


async def _bind_shared_research_scope(session: AsyncSession) -> None:
    await session.execute(select(func.set_config("app.research_tenant_id", TENANT_ID, True)))
    await session.execute(select(func.set_config("app.research_market", MARKET, True)))


async def _entitlement(session: AsyncSession, *, on_date: dt.date) -> ResearchDataEntitlement:
    row = await session.scalar(
        select(ResearchDataEntitlement).where(
            ResearchDataEntitlement.tenant_id == TENANT_ID,
            ResearchDataEntitlement.market == MARKET,
            ResearchDataEntitlement.dataset_key == DATASET_KEY,
        )
    )
    if row is None or not entitlement_allows_internal_research(row, on_date=on_date):
        raise PermissionError(
            "Cboe Option Sentiment import requires an approved, current internal-research "
            "and retention entitlement"
        )
    return row


async def _security_aliases(session: AsyncSession) -> list[SecurityAlias]:
    rows = list(
        await session.scalars(
            select(SecurityMaster).where(SecurityMaster.market == MARKET)
        )
    )
    return [
        SecurityAlias(
            canonical_code=row.symbol,
            aliases=tuple(
                sorted(
                    {
                        value.strip()
                        for value in (
                            row.symbol,
                            row.raw_symbol,
                            row.cqs_symbol,
                            row.nasdaq_symbol,
                        )
                        if value and value.strip()
                    }
                )
            ),
        )
        for row in rows
    ]


def _object_key(*, kind: str, digest: str, trade_date: dt.date, suffix: str) -> str:
    return (
        f"us/options/{DATASET_KEY}/{kind}/year={trade_date.year}/"
        f"month={trade_date.month:02d}/date={trade_date.isoformat()}/"
        f"{digest}{suffix}"
    )


def _read_bounded_regular_file(path: Path) -> bytes:
    """Read one operator delivery without following symlinks or accepting special files."""

    limit = MAX_ARCHIVE_BYTES if path.suffix.lower() == ".zip" else MAX_CSV_BYTES
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"cannot safely open option sentiment input: {path}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("option sentiment input must be a regular file")
        if metadata.st_size > limit:
            raise ValueError(f"option sentiment input exceeds {limit} bytes")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            payload = handle.read(limit + 1)
        if len(payload) > limit:
            raise ValueError(f"option sentiment input exceeds {limit} bytes")
        return payload
    finally:
        os.close(descriptor)


async def import_option_sentiment(
    session: AsyncSession,
    *,
    path: str | Path,
    known_at: dt.datetime,
    completeness: OptionSentimentCompleteness,
    source_revision: str,
    delivery_mode: OptionSentimentDeliveryMode = "historical",
    store: ImmutableObjectStore | None = None,
    settings: Settings | None = None,
) -> ResearchDatasetSnapshot:
    """Import one operator-supplied Cboe delivery after all entitlement and quality gates."""

    configured = settings or get_settings()
    if not configured.us_options_phase_a_enabled:
        raise RuntimeError("US options Phase A ingestion is disabled")
    if completeness not in {"preliminary", "complete", "sample"}:
        raise ValueError("completeness must be preliminary, complete, or sample")
    revision = source_revision.strip()
    if not revision:
        raise ValueError("source_revision is required")
    if len(revision) > 96:
        raise ValueError("source_revision must be at most 96 characters")
    if delivery_mode not in {"historical", "subscription"}:
        raise ValueError("delivery_mode must be historical or subscription")
    if known_at.tzinfo is None or known_at.utcoffset() is None:
        raise ValueError("known_at must be timezone-aware")

    await _bind_shared_research_scope(session)
    entitlement = await _entitlement(session, on_date=known_at.date())
    source_path = Path(path)
    payload = await asyncio.to_thread(_read_bounded_regular_file, source_path)
    raw_sha = hashlib.sha256(payload).hexdigest()
    parsed = parse_cboe_option_sentiment(
        payload,
        source_filename=source_path.name,
        completeness=completeness,
        known_at=known_at,
    )
    effective_at = dt.datetime.combine(
        parsed.trade_date,
        dt.time(16, 0),
        tzinfo=_EASTERN,
    ).astimezone(dt.UTC)
    if parsed.known_at < effective_at:
        raise ValueError("known_at cannot precede the completed US session")

    existing = await session.scalar(
        select(ResearchDatasetSnapshot).where(
            ResearchDatasetSnapshot.tenant_id == TENANT_ID,
            ResearchDatasetSnapshot.market == MARKET,
            ResearchDatasetSnapshot.dataset_key == DATASET_KEY,
            ResearchDatasetSnapshot.trade_date == parsed.trade_date,
            ResearchDatasetSnapshot.completeness == completeness,
            ResearchDatasetSnapshot.source_revision == revision,
        )
    )
    if existing is not None:
        if existing.raw_sha256 != raw_sha:
            raise RuntimeError(
                "source_revision already identifies different immutable source bytes"
            )
        return existing

    normalized, quality, fingerprint = normalize_option_sentiment(
        parsed.rows,
        securities=await _security_aliases(session),
        completeness=completeness,
        minimum_identity_coverage=configured.us_options_min_identity_coverage,
    )
    parquet_payload = option_sentiment_parquet(normalized)
    parquet_sha = hashlib.sha256(parquet_payload).hexdigest()
    target = store or object_store(configured)
    raw_suffix = ".zip" if payload.startswith(b"PK\x03\x04") else ".csv"
    raw_object = target.put(
        key=_object_key(
            kind="raw",
            digest=raw_sha,
            trade_date=parsed.trade_date,
            suffix=raw_suffix,
        ),
        payload=payload,
        content_type="application/zip" if raw_suffix == ".zip" else "text/csv",
        metadata={"dataset": DATASET_KEY, "trade-date": parsed.trade_date.isoformat()},
    )
    normalized_object = target.put(
        key=_object_key(
            kind=f"normalized/schema={CBOE_OPTION_SENTIMENT_SCHEMA_VERSION}",
            digest=parquet_sha,
            trade_date=parsed.trade_date,
            suffix=".parquet",
        ),
        payload=parquet_payload,
        content_type="application/vnd.apache.parquet",
        metadata={
            "dataset": DATASET_KEY,
            "trade-date": parsed.trade_date.isoformat(),
            "dataset-fingerprint": fingerprint,
        },
    )
    snapshot = ResearchDatasetSnapshot(
        tenant_id=TENANT_ID,
        market=MARKET,
        entitlement_id=entitlement.id,
        dataset_key=DATASET_KEY,
        provider=PROVIDER,
        trade_date=parsed.trade_date,
        completeness=completeness,
        source_revision=revision,
        schema_version=CBOE_OPTION_SENTIMENT_SCHEMA_VERSION,
        normalization_version=NORMALIZATION_VERSION,
        identity_version=IDENTITY_VERSION,
        effective_at=effective_at,
        known_at=parsed.known_at,
        status="accepted" if quality.passed else "rejected",
        row_count=len(normalized),
        raw_object_key=raw_object.key,
        raw_sha256=raw_object.sha256,
        normalized_object_key=normalized_object.key,
        normalized_sha256=normalized_object.sha256,
        dataset_fingerprint=fingerprint,
        quality_report=quality.model_dump(mode="json"),
        source_metadata={
            "source_filename": source_path.name,
            "source_specification": _SPEC_URL,
            "delivery_mode": delivery_mode,
            "open_interest_semantics": "previous_settlement",
            "coverage": "US-listed stock, ETF, and index options in the vendor delivery",
            "customer_serving_enabled": False,
        },
    )
    session.add(snapshot)
    await session.flush()
    return snapshot
