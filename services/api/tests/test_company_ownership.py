from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest

from api.routers.company import _ownership_from_snapshots
from bulls.core.models import ShareholdingSnapshot


def _snapshot(
    as_of: dt.date,
    *,
    sponsor: float,
    institute: float,
    foreign: float,
    public: float,
    govt: float = 0.0,
) -> ShareholdingSnapshot:
    return ShareholdingSnapshot(
        market="DSE",
        code="EBL",
        as_of_date=as_of,
        sponsor_director=sponsor,
        govt=govt,
        institute=institute,
        foreign_pct=foreign,
        public=public,
    )


def test_ownership_uses_latest_two_disclosures_for_values_and_deltas() -> None:
    ownership = _ownership_from_snapshots(
        [
            _snapshot(
                dt.date(2025, 12, 31),
                sponsor=31.44,
                institute=41.41,
                foreign=0.67,
                public=26.48,
            ),
            _snapshot(
                dt.date(2026, 5, 31),
                sponsor=31.44,
                institute=42.82,
                foreign=0.67,
                public=25.07,
            ),
            _snapshot(
                dt.date(2026, 6, 30),
                sponsor=29.44,
                institute=44.42,
                foreign=0.67,
                public=25.47,
            ),
        ]
    )

    assert ownership.as_of == "2026-06-30"
    assert ownership.sponsor_pct == pytest.approx(29.44)
    assert ownership.institute_pct == pytest.approx(44.42)
    assert ownership.public_pct == pytest.approx(25.47)
    assert ownership.sponsor_delta == pytest.approx(-2.0)
    assert ownership.institute_delta == pytest.approx(1.6)
    assert ownership.public_delta == pytest.approx(0.4)
    assert ownership.foreign_delta == pytest.approx(0.0)
    assert ownership.govt_delta == pytest.approx(0.0)
    assert ownership.composition_total == pytest.approx(100.0)
    assert [point.as_of for point in ownership.history] == [
        "2025-12-31",
        "2026-05-31",
        "2026-06-30",
    ]


def test_ownership_excludes_invalid_latest_snapshot_defensively() -> None:
    valid = _snapshot(
        dt.date(2026, 5, 31),
        sponsor=31.44,
        institute=42.82,
        foreign=0.67,
        public=25.07,
    )
    corrupt = _snapshot(
        dt.date(2026, 6, 30),
        sponsor=0.0,
        institute=0.0,
        foreign=0.0,
        public=0.0,
    )

    ownership = _ownership_from_snapshots([valid, corrupt])

    assert ownership.as_of == "2026-05-31"
    assert ownership.sponsor_pct == pytest.approx(31.44)
    assert ownership.sponsor_delta is None
    assert len(ownership.history) == 1


def test_ownership_returns_empty_contract_when_no_snapshot_is_valid() -> None:
    corrupt = _snapshot(
        dt.date(2026, 6, 30),
        sponsor=120.0,
        institute=0.0,
        foreign=0.0,
        public=-20.0,
    )

    ownership = _ownership_from_snapshots([corrupt])

    assert ownership.as_of is None
    assert ownership.composition_total is None
    assert ownership.history == []


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres")
@pytest.mark.asyncio
async def test_database_rejects_invalid_shareholding_composition() -> None:
    from sqlalchemy.exc import IntegrityError

    from bulls.core.db import dispose_engine, get_sessionmaker

    await dispose_engine()
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        session.add(
            ShareholdingSnapshot(
                market="DSE",
                code="T" + uuid.uuid4().hex[:8].upper(),
                as_of_date=dt.date(2026, 7, 1),
                sponsor_director=0.0,
                govt=0.0,
                institute=0.0,
                foreign_pct=0.0,
                public=0.0,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
