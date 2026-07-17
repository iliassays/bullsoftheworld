"""Shared immutable-lineage writers for operational ingestion jobs."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import uuid
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.models import (
    CompanyDataObservation,
    DailyBarObservation,
    DataSourceSnapshot,
    SecFinancialFactObservation,
    SecurityListingObservation,
)

LINEAGE_SCHEMA_VERSION = "1"
BAR_NORMALIZATION_VERSION = "daily-bar-v1"
COMPANY_NORMALIZATION_VERSION = "company-info-v1"
SEC_FACT_NORMALIZATION_VERSION = "sec-company-facts-v1"
SECURITY_MASTER_NORMALIZATION_VERSION = "us-security-master-v1"
LINEAGE_INSERT_BATCH_ROWS = 500


@lru_cache(maxsize=1)
def current_code_version() -> str:
    """Resolve one stable release identity per process without requiring shell environment setup."""

    configured = (os.getenv("RELEASE_VERSION") or os.getenv("GIT_SHA") or "").strip()
    if configured and configured != "unknown":
        return configured[:96]
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    resolved = completed.stdout.strip()
    return resolved[:96] if resolved else "unknown"


def _json_default(value: Any) -> str:
    if isinstance(value, dt.date | dt.datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    raise TypeError(f"cannot serialize {type(value).__name__} for lineage")


def canonical_json(value: Any) -> str:
    """Return a deterministic, strict JSON representation for hashes and manifests."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=_json_default,
    )


def content_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


async def _insert_observation_batches(
    session,
    model,
    rows: list[dict[str, Any]],
    *,
    index_elements: list[str],
) -> int:
    inserted = 0
    for start in range(0, len(rows), LINEAGE_INSERT_BATCH_ROWS):
        batch = rows[start : start + LINEAGE_INSERT_BATCH_ROWS]
        result = await session.execute(
            pg_insert(model).values(batch).on_conflict_do_nothing(index_elements=index_elements)
        )
        if result.rowcount and result.rowcount > 0:
            inserted += int(result.rowcount)
    return inserted


async def persist_source_snapshot(
    session,
    *,
    market: str,
    dataset_key: str,
    provider: str,
    scope_key: str,
    normalized_records: Sequence[Mapping[str, Any]],
    normalization_version: str,
    known_at: dt.datetime,
    effective_at: dt.datetime | None = None,
    quality_report: Mapping[str, Any] | None = None,
    source_metadata: Mapping[str, Any] | None = None,
    raw_object_key: str | None = None,
    raw_sha256: str | None = None,
) -> uuid.UUID:
    """Insert or resolve an immutable manifest for an idempotent normalized delivery."""
    normalized = list(normalized_records)
    normalized_sha256 = content_sha256(normalized)
    code_version = current_code_version()
    values = {
        "market": market,
        "dataset_key": dataset_key,
        "provider": provider,
        "scope_key": scope_key,
        "source_revision": normalized_sha256,
        "schema_version": LINEAGE_SCHEMA_VERSION,
        "normalization_version": normalization_version,
        "code_version": code_version,
        "effective_at": effective_at,
        "known_at": known_at,
        "status": "accepted",
        "row_count": len(normalized),
        "raw_object_key": raw_object_key,
        "raw_sha256": raw_sha256,
        "normalized_sha256": normalized_sha256,
        "quality_report": dict(quality_report or {}),
        "source_metadata": dict(source_metadata or {}),
    }
    stmt = (
        pg_insert(DataSourceSnapshot)
        .values(values)
        .on_conflict_do_nothing(
            index_elements=["market", "dataset_key", "scope_key", "source_revision"]
        )
        .returning(DataSourceSnapshot.id)
    )
    snapshot_id = (await session.execute(stmt)).scalar_one_or_none()
    if snapshot_id is not None:
        return snapshot_id
    existing = await session.scalar(
        select(DataSourceSnapshot).where(
            DataSourceSnapshot.market == market,
            DataSourceSnapshot.dataset_key == dataset_key,
            DataSourceSnapshot.scope_key == scope_key,
            DataSourceSnapshot.source_revision == normalized_sha256,
        )
    )
    if existing is None:
        raise RuntimeError("source snapshot conflict did not resolve to a persisted manifest")
    if existing.code_version == "unknown" and code_version != "unknown":
        await session.execute(
            update(DataSourceSnapshot)
            .where(
                DataSourceSnapshot.id == existing.id,
                DataSourceSnapshot.code_version == "unknown",
            )
            .values(code_version=code_version)
        )
    return existing.id


def _bar_row(bar) -> dict[str, Any]:
    return {
        "market": bar.market,
        "code": bar.code,
        "date": bar.date,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "adjusted_close": bar.adjusted_close,
        "source": bar.source,
    }


async def record_daily_bar_observations(
    session,
    bars: Sequence,
    *,
    observed_at: dt.datetime,
    knowledge_time_quality: str = "ingestion_upper_bound",
) -> int:
    if not bars:
        return 0
    normalized = [_bar_row(bar) for bar in sorted(bars, key=lambda item: item.date)]
    market = normalized[0]["market"]
    code = normalized[0]["code"]
    if any(row["market"] != market or row["code"] != code for row in normalized):
        raise ValueError("one daily-bar source snapshot must contain exactly one market/symbol")
    provider = str(normalized[0]["source"] or "unknown")
    latest_date = max(row["date"] for row in normalized)
    snapshot_id = await persist_source_snapshot(
        session,
        market=market,
        dataset_key="daily_bars",
        provider=provider,
        scope_key=code,
        normalized_records=normalized,
        normalization_version=BAR_NORMALIZATION_VERSION,
        known_at=observed_at,
        effective_at=dt.datetime.combine(latest_date, dt.time.max, tzinfo=dt.UTC),
        source_metadata={
            "first_date": min(row["date"] for row in normalized).isoformat(),
            "last_date": latest_date.isoformat(),
            "raw_archive_available": False,
            "knowledge_time_quality": knowledge_time_quality,
        },
    )
    rows = [
        {
            "source_snapshot_id": snapshot_id,
            **row,
            "known_at": observed_at,
            "knowledge_time_quality": knowledge_time_quality,
            "row_sha256": content_sha256(row),
        }
        for row in normalized
    ]
    return await _insert_observation_batches(
        session,
        DailyBarObservation,
        rows,
        index_elements=["market", "code", "date", "row_sha256"],
    )


def _company_records(info) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = [
        {
            "record_type": "profile",
            "natural_key": "current",
            "effective_date": None,
            "payload": info.profile.model_dump(mode="json"),
        }
    ]
    records.extend(
        {
            "record_type": "shareholding",
            "natural_key": row.as_of_date.isoformat(),
            "effective_date": row.as_of_date,
            "payload": row.model_dump(mode="json"),
        }
        for row in info.shareholdings
    )
    records.extend(
        {
            "record_type": "annual_financial",
            "natural_key": str(row.fiscal_year),
            "effective_date": None,
            "payload": row.model_dump(mode="json"),
        }
        for row in info.financials
    )
    records.extend(
        {
            "record_type": "dividend",
            "natural_key": str(row.year),
            "effective_date": None,
            "payload": row.model_dump(mode="json"),
        }
        for row in info.dividends
    )
    return records


async def record_company_data_observations(
    session,
    info,
    *,
    observed_at: dt.datetime,
) -> int:
    records = _company_records(info)
    market = info.profile.market
    code = info.profile.code
    snapshot_id = await persist_source_snapshot(
        session,
        market=market,
        dataset_key="company_data",
        provider="dse_company_page" if market == "DSE" else "company_provider",
        scope_key=code,
        normalized_records=records,
        normalization_version=COMPANY_NORMALIZATION_VERSION,
        known_at=observed_at,
        source_metadata={"raw_archive_available": False},
    )
    rows = []
    for record in records:
        payload = record["payload"]
        row_hash = content_sha256(
            {
                "record_type": record["record_type"],
                "natural_key": record["natural_key"],
                "payload": payload,
            }
        )
        rows.append(
            {
                "source_snapshot_id": snapshot_id,
                "market": market,
                "code": code,
                "record_type": record["record_type"],
                "natural_key": record["natural_key"],
                "effective_date": record["effective_date"],
                "known_at": observed_at,
                "source": "dse_company_page" if market == "DSE" else "company_provider",
                "payload": payload,
                "row_sha256": row_hash,
            }
        )
    return await _insert_observation_batches(
        session,
        CompanyDataObservation,
        rows,
        index_elements=["market", "code", "record_type", "natural_key", "row_sha256"],
    )


def sec_fact_known_at(fact, accepted_at: dt.datetime | None) -> dt.datetime:
    if accepted_at is not None:
        return accepted_at.replace(tzinfo=accepted_at.tzinfo or dt.UTC)
    return dt.datetime.combine(fact.filed_at, dt.time.max, tzinfo=dt.UTC)


async def record_sec_fact_observations(
    session,
    *,
    code: str,
    facts: Sequence,
    filings: Sequence,
    observed_at: dt.datetime,
) -> int:
    normalized = [fact.model_dump(mode="json") for fact in facts]
    snapshot_id = await persist_source_snapshot(
        session,
        market="US",
        dataset_key="sec_company_facts",
        provider="sec_edgar",
        scope_key=code,
        normalized_records=normalized,
        normalization_version=SEC_FACT_NORMALIZATION_VERSION,
        known_at=observed_at,
        source_metadata={"raw_archive_available": False},
    )
    accepted_by_accession = {filing.accession_number: filing.accepted_at for filing in filings}
    rows = []
    for fact in facts:
        payload = fact.model_dump()
        accepted_at = accepted_by_accession.get(fact.accession_number)
        rows.append(
            {
                "source_snapshot_id": snapshot_id,
                **payload,
                "accepted_at": accepted_at,
                "known_at": sec_fact_known_at(fact, accepted_at),
                "normalization_version": SEC_FACT_NORMALIZATION_VERSION,
                "row_sha256": content_sha256(fact.model_dump(mode="json")),
            }
        )
    return await _insert_observation_batches(
        session,
        SecFinancialFactObservation,
        rows,
        index_elements=[
            "market",
            "code",
            "metric",
            "period_end",
            "period_type",
            "accession_number",
            "row_sha256",
        ],
    )


async def record_security_listing_events(session, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    return await _insert_observation_batches(
        session,
        SecurityListingObservation,
        rows,
        index_elements=["source_snapshot_id", "market", "symbol"],
    )
