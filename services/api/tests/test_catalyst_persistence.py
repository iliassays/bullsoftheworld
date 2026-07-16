from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.dialects import postgresql

from api.institutional_research.catalysts import (
    _catalyst_upsert_statement,
    _dse_announcement_url,
)


def test_dse_source_url_targets_the_exact_announcement_date() -> None:
    url = _dse_announcement_url(dt.date(2026, 7, 16))

    assert "startDate=2026-07-16" in url
    assert "endDate=2026-07-16" in url
    assert "archive=news" in url


def test_catalyst_upsert_uses_stable_source_identity_and_preserves_cancellations() -> None:
    statement = _catalyst_upsert_statement(
        [
            {
                "id": uuid.uuid4(),
                "tenant_id": "bullsofwallst",
                "market": "US",
                "code": "ABCD",
                "event_type": "periodic_report_window",
                "title": "ABCD expected periodic report",
                "timing_kind": "window",
                "confirmed_date": None,
                "window_start": dt.date(2026, 8, 1),
                "window_end": dt.date(2026, 8, 20),
                "status": "scheduled",
                "confidence": "inferred_cadence",
                "source_type": "sec_filing_cadence",
                "source_ref": "0000000000-26-000001",
                "source_url": "https://www.sec.gov/Archives/example.htm",
                "known_at": dt.datetime(2026, 5, 8, 20, 31, tzinfo=dt.UTC),
                "expected_evidence": "Quarterly filing",
                "details": {"cadence_days": 91},
                "dedupe_key": "a" * 64,
            }
        ]
    )

    sql = str(statement.compile(dialect=postgresql.dialect())).lower()

    assert "on conflict on constraint uq_research_catalyst_source_event" in sql
    assert "status = case" in sql
    assert "research_catalyst_events.status = " in sql
    assert "dedupe_key = excluded.dedupe_key" in sql
