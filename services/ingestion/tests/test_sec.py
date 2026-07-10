from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.dialects import postgresql

from bulls.core.models import SecFiling
from bulls.market_data.providers.sec_edgar import SecFinancialFactRecord, SecIssuerProfile
from ingestion.sec import _profile_row, _sector_from_sic, _ttm_value, _upsert


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
