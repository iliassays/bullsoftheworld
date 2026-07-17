from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.dialects import postgresql

from api.institutional_research.catalysts import (
    _calendar_statement,
    _catalyst_upsert_statement,
    _dse_announcement_url,
    _superseded_us_forecasts_statement,
    _us_source_backfill_statement,
)
from bulls.analytics.catalysts import CatalystDraft


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


def test_us_maintenance_backfills_sources_and_cancels_only_superseded_forecasts() -> None:
    source_sql = str(
        _us_source_backfill_statement("bullsofwallst", "US").compile(
            dialect=postgresql.dialect()
        )
    ).lower()
    draft = CatalystDraft(
        market="US",
        code="SOBR",
        event_type="periodic_report_window",
        title="SOBR expected periodic report",
        timing_kind="window",
        window_start=dt.date(2026, 8, 1),
        window_end=dt.date(2026, 8, 20),
        confidence="inferred_cadence",
        source_type="sec_filing_cadence",
        source_ref="current-accession",
        source_url="https://www.sec.gov/current.htm",
        known_at=dt.datetime(2026, 5, 8, 20, 31, tzinfo=dt.UTC),
    )
    superseded = _superseded_us_forecasts_statement("bullsofwallst", "US", [draft])

    assert superseded is not None
    compiled_superseded = superseded.compile(dialect=postgresql.dialect())
    superseded_sql = str(compiled_superseded).lower()
    assert "sec_filings.filing_url" in source_sql
    assert "source_url is null" in source_sql
    assert "(research_catalyst_events.code, research_catalyst_events.source_ref) not in" in (
        superseded_sql
    )
    assert compiled_superseded.params["status"] == "cancelled"
    assert ("SOBR", "current-accession") in compiled_superseded.params["param_1"]


def test_us_supersession_is_skipped_when_no_current_forecast_exists() -> None:
    assert _superseded_us_forecasts_statement("bullsofwallst", "US", []) is None


def test_us_calendar_read_rechecks_current_product_eligibility() -> None:
    statement = _calendar_statement(
        tenant_id="bullsofwallst",
        market="US",
        earliest=dt.date(2026, 7, 10),
        latest=dt.date(2026, 8, 10),
        code=None,
    )
    sql = str(statement.compile(dialect=postgresql.dialect())).lower()

    assert "join symbols" in sql
    assert "join security_master" in sql
    assert "symbols.is_active is true" in sql
    assert "security_master.is_product_eligible is true" in sql
