from __future__ import annotations

import datetime as dt

import httpx
import pytest
from sqlalchemy.dialects import postgresql

from bulls.core.models import SecFiling
from bulls.market_data.providers.sec_edgar import SecFinancialFactRecord, SecIssuerProfile
from ingestion.sec import _profile_row, _sector_from_sic, _ttm_value, _upsert
from ingestion.sec_13f import (
    MAPPING_SCOPE,
    UPSERT_BATCH_ROWS,
    _archive_sequence,
    _is_consecutive_report_pair,
    _is_refresh_current,
    _retry_delay,
    _retryable_http_error,
    _upsert_managers,
)
from ingestion.sec_13f import _upsert as _upsert_13f


def _fact(
    metric: str,
    value: float,
    end: dt.date,
    period_type: str,
) -> SecFinancialFactRecord:
    return SecFinancialFactRecord(
        code="TEST",
        metric=metric,
        value=value,
        unit="USD" if metric != "shares_outstanding" else "shares",
        period_start=end - dt.timedelta(days=90) if period_type != "instant" else None,
        period_end=end,
        period_type=period_type,
        fiscal_year=end.year,
        fiscal_period="Q1",
        form="10-K" if period_type == "annual" else "10-Q",
        filed_at=end + dt.timedelta(days=40),
        accession_number="0000000001-26-000001",
        taxonomy="us-gaap",
        source_concept=metric,
        source_url="https://www.sec.gov/example",
    )


def test_ttm_rolls_latest_quarter_over_prior_annual_period() -> None:
    facts = [
        _fact("net_income", 100, dt.date(2025, 12, 31), "annual"),
        _fact("net_income", 20, dt.date(2025, 3, 31), "quarter"),
        _fact("net_income", 30, dt.date(2026, 3, 31), "quarter"),
    ]

    assert _ttm_value(facts, "net_income") == 110


def test_adr_profile_does_not_assume_issuer_shares_equal_ads() -> None:
    facts = [
        _fact("shares_outstanding", 1_000, dt.date(2026, 3, 31), "instant"),
        _fact("net_income", 500, dt.date(2025, 12, 31), "annual"),
    ]
    issuer = SecIssuerProfile(cik=1, name="Foreign Issuer", sic="7372")

    row = _profile_row(
        "ADR",
        issuer,
        facts,
        dt.datetime(2026, 7, 10, tzinfo=dt.UTC),
        "adr",
        False,
    )

    assert row["instrument_type"] == "adr"
    assert row["outstanding_shares"] is None
    assert row["eps"] is None
    assert row["nav_per_share"] is None


def test_sic_mapping_produces_comparable_retail_sectors() -> None:
    assert _sector_from_sic("3571", "Electronic Computers") == "Technology"
    assert _sector_from_sic("6021", "National Commercial Banks") == "Financials"
    assert _sector_from_sic("2834", "Pharmaceutical Preparations") == "Health Care"


def test_13f_refresh_state_requires_requested_history_depth() -> None:
    url = "https://www.sec.gov/files/current.zip"
    details = {
        "current_archive_url": url,
        "history_quarters_loaded": 4,
        "mapping_scope": MAPPING_SCOPE,
    }

    assert _is_refresh_current(details, url, 4)
    assert not _is_refresh_current(details, url, 8)
    assert not _is_refresh_current(details, "https://www.sec.gov/files/new.zip", 1)


def test_legacy_13f_refresh_state_is_rebuilt_for_full_reference_scope() -> None:
    url = "https://www.sec.gov/files/current.zip"

    assert not _is_refresh_current({"current_archive_url": url}, url, 1)
    assert not _is_refresh_current({"current_archive_url": url}, url, 2)


def test_13f_http_retry_is_bounded_to_transient_failures() -> None:
    request = httpx.Request("GET", "https://www.sec.gov/example")
    unavailable = httpx.HTTPStatusError(
        "unavailable",
        request=request,
        response=httpx.Response(503, headers={"Retry-After": "7"}, request=request),
    )
    not_found = httpx.HTTPStatusError(
        "not found",
        request=request,
        response=httpx.Response(404, request=request),
    )

    assert _retryable_http_error(unavailable)
    assert _retry_delay(unavailable, 0) == 7
    assert not _retryable_http_error(not_found)
    assert _retry_delay(httpx.ConnectError("offline", request=request), 2) == 20


def test_forced_13f_recovery_derives_only_validated_official_quarter_windows() -> None:
    checkpoint = (
        "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/"
        "01mar2026-31may2026_form13f.zip"
    )

    assert _archive_sequence(checkpoint, 3) == [
        checkpoint,
        "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/"
        "01dec2025-28feb2026_form13f.zip",
        "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/"
        "01sep2025-30nov2025_form13f.zip",
    ]
    assert _archive_sequence(checkpoint.replace("www.sec.gov", "example.com"), 3) == []
    assert _archive_sequence(checkpoint.replace("31may2026", "30may2026"), 3) == []


def test_13f_comparisons_require_adjacent_quarter_ends() -> None:
    assert _is_consecutive_report_pair(dt.date(2026, 3, 31), dt.date(2025, 12, 31))
    assert _is_consecutive_report_pair(dt.date(2024, 3, 31), dt.date(2023, 12, 31))
    assert not _is_consecutive_report_pair(dt.date(2026, 3, 31), dt.date(2025, 9, 30))
    assert not _is_consecutive_report_pair(dt.date(2026, 3, 30), dt.date(2025, 12, 31))


@pytest.mark.asyncio
async def test_historical_13f_import_does_not_regress_manager_latest_dates() -> None:
    class Session:
        statement = None

        async def execute(self, statement):
            self.statement = statement

    session = Session()
    await _upsert_managers(
        session,
        [
            {
                "cik": 1,
                "name": "Example Manager",
                "latest_report_date": dt.date(2025, 12, 31),
                "latest_filing_date": dt.date(2026, 2, 14),
                "updated_at": dt.datetime(2026, 2, 14, tzinfo=dt.UTC),
            }
        ],
    )

    sql = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "name = case" in sql.lower()
    assert "greatest(institutional_managers.latest_report_date" in sql.lower()
    assert "greatest(institutional_managers.latest_filing_date" in sql.lower()


@pytest.mark.asyncio
async def test_upsert_uses_excluded_column_when_name_collides_with_collection_method() -> None:
    class Session:
        statement = None

        async def execute(self, statement):
            self.statement = statement

    session = Session()
    await _upsert(
        session,
        SecFiling,
        [
            {
                "market": "US",
                "code": "AAPL",
                "accession_number": "0000320193-26-000001",
                "items": "2.02",
            }
        ],
        ("market", "code", "accession_number"),
    )

    sql = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "items = excluded.items" in sql


@pytest.mark.asyncio
async def test_13f_upsert_batches_below_asyncpg_parameter_limit() -> None:
    class Session:
        def __init__(self) -> None:
            self.statements = []

        async def execute(self, statement):
            self.statements.append(statement)

    session = Session()
    rows = [
        {
            "market": "US",
            "code": f"T{index}",
            "accession_number": f"0000000001-26-{index:06d}",
            "items": None,
        }
        for index in range(UPSERT_BATCH_ROWS * 2 + 1)
    ]

    await _upsert_13f(
        session,
        SecFiling,
        rows,
        ("market", "code", "accession_number"),
    )

    assert len(session.statements) == 3
