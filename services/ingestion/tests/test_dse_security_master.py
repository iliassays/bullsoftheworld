import datetime as dt

import pytest

from bulls.market_data import Symbol
from ingestion.dse_security_master import (
    MINIMUM_LIVE_RECORDS,
    persist_dse_listing_snapshot,
    validate_dse_listing_snapshot,
)


def _records(count: int = MINIMUM_LIVE_RECORDS) -> list[Symbol]:
    return [
        Symbol(
            market="DSE",
            code=f"DSE{index:04d}",
            name_en=f"DSE company {index}",
            sector="Engineering",
            category="A",
        )
        for index in range(count)
    ]


def test_dse_listing_snapshot_accepts_complete_unique_market_delivery() -> None:
    quality = validate_dse_listing_snapshot(
        _records(400),
        previous_active_count=401,
    )

    assert quality.records == 400
    assert quality.coverage_ratio == pytest.approx(400 / 401)


def test_dse_listing_snapshot_rejects_duplicate_symbols() -> None:
    records = _records()
    records[-1] = records[0]

    with pytest.raises(ValueError, match="duplicate symbols"):
        validate_dse_listing_snapshot(records)


def test_dse_listing_snapshot_rejects_coverage_collapse_before_removals() -> None:
    with pytest.raises(ValueError, match="coverage collapsed"):
        validate_dse_listing_snapshot(
            _records(300),
            previous_active_count=400,
        )


def test_dse_listing_snapshot_rejects_cross_market_input() -> None:
    records = _records()
    records[0] = records[0].model_copy(update={"market": "US"})

    with pytest.raises(ValueError, match="non-DSE"):
        validate_dse_listing_snapshot(records)


@pytest.mark.asyncio
async def test_dse_listing_snapshot_requires_explicit_knowledge_timezone() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        await persist_dse_listing_snapshot(
            None,
            _records(),
            observed_at=dt.datetime(2026, 7, 18, 12),
        )
