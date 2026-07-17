from __future__ import annotations

import datetime as dt
import uuid
from types import SimpleNamespace

import pytest

from bulls.core.models import SecurityListingObservation
from ingestion.lineage import (
    LINEAGE_INSERT_BATCH_ROWS,
    _insert_observation_batches,
    canonical_json,
    content_sha256,
    record_sec_fact_observations,
    sec_fact_known_at,
)


def test_canonical_hash_is_order_independent_for_mapping_keys() -> None:
    first = {
        "code": "AAPL",
        "date": dt.date(2026, 7, 17),
        "values": {"close": 200, "open": 199},
    }
    second = {
        "values": {"open": 199, "close": 200},
        "date": dt.date(2026, 7, 17),
        "code": "AAPL",
    }

    assert canonical_json(first) == canonical_json(second)
    assert content_sha256(first) == content_sha256(second)
    assert len(content_sha256(first)) == 64


def test_canonical_hash_rejects_non_finite_financial_values() -> None:
    with pytest.raises(ValueError, match="Out of range float"):
        content_sha256({"close": float("nan")})


def test_sec_fact_known_time_prefers_official_acceptance_timestamp() -> None:
    accepted_at = dt.datetime(2026, 5, 1, 20, 15, tzinfo=dt.UTC)
    fact = SimpleNamespace(filed_at=dt.date(2026, 5, 1))

    assert sec_fact_known_at(fact, accepted_at) == accepted_at


def test_sec_fact_known_time_falls_back_conservatively_to_end_of_filing_day() -> None:
    fact = SimpleNamespace(filed_at=dt.date(2026, 5, 1))

    known_at = sec_fact_known_at(fact, None)

    assert known_at.date() == fact.filed_at
    assert known_at.time() == dt.time.max
    assert known_at.tzinfo == dt.UTC


@pytest.mark.asyncio
async def test_observation_writes_are_batched_below_driver_parameter_limits() -> None:
    class Result:
        def __init__(self, rowcount: int) -> None:
            self.rowcount = rowcount

    class Session:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, _statement):
            self.calls += 1
            remaining = LINEAGE_INSERT_BATCH_ROWS * 2 + 1
            return Result(
                min(
                    LINEAGE_INSERT_BATCH_ROWS,
                    remaining - (self.calls - 1) * LINEAGE_INSERT_BATCH_ROWS,
                )
            )

    session = Session()
    rows = [{"market": "US"} for _ in range(LINEAGE_INSERT_BATCH_ROWS * 2 + 1)]

    inserted = await _insert_observation_batches(
        session,
        SecurityListingObservation,
        rows,
        index_elements=["source_snapshot_id", "market", "symbol"],
    )

    assert session.calls == 3
    assert inserted == len(rows)


@pytest.mark.asyncio
async def test_empty_sec_fact_delivery_still_persists_an_accepted_source_manifest(
    monkeypatch,
) -> None:
    calls: dict[str, object] = {}

    async def fake_snapshot(_session, **kwargs):
        calls["normalized_records"] = kwargs["normalized_records"]
        return uuid.uuid4()

    async def fake_insert(_session, _model, rows, *, index_elements):
        calls["rows"] = rows
        calls["index_elements"] = index_elements
        return 0

    monkeypatch.setattr("ingestion.lineage.persist_source_snapshot", fake_snapshot)
    monkeypatch.setattr("ingestion.lineage._insert_observation_batches", fake_insert)

    inserted = await record_sec_fact_observations(
        object(),
        code="EMPTY",
        facts=[],
        filings=[],
        observed_at=dt.datetime(2026, 7, 17, tzinfo=dt.UTC),
    )

    assert inserted == 0
    assert calls["normalized_records"] == []
    assert calls["rows"] == []
