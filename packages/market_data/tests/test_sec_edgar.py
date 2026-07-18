from __future__ import annotations

import datetime as dt

import httpx
import pytest

from bulls.market_data.providers.sec_edgar import (
    SecEdgarClient,
    filing_category,
    parse_company_fact_observations,
    parse_company_facts,
    parse_submissions,
)


@pytest.mark.asyncio
async def test_missing_company_facts_does_not_hide_valid_submissions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/submissions/"):
            return httpx.Response(200, json={"cik": 1, "filings": {"recent": {}}})
        return httpx.Response(404, json={"message": "not found"})

    client = SecEdgarClient(
        "BullsOfTheWorld/1.0 monitored@example.com",
        requests_per_second=10_000,
        transport=httpx.MockTransport(handler),
    )

    submissions, company_facts = await client.fetch_company(1)

    assert submissions["cik"] == 1
    assert company_facts == {}


def test_parse_submissions_keeps_material_recent_filings() -> None:
    payload = {
        "cik": "320193",
        "name": "Apple Inc.",
        "sic": "3571",
        "sicDescription": "Electronic Computers",
        "fiscalYearEnd": "0926",
        "stateOfIncorporation": "CA",
        "filings": {
            "recent": {
                "accessionNumber": ["0000320193-26-000001", "0000320193-15-000001"],
                "filingDate": ["2026-05-01", "2015-01-01"],
                "reportDate": ["2026-03-28", "2014-12-31"],
                "acceptanceDateTime": ["2026-05-01T16:01:02.000Z", "2015-01-01T00:00:00Z"],
                "form": ["10-Q", "10-K"],
                "primaryDocument": ["aapl-20260328.htm", "old.htm"],
                "primaryDocDescription": ["Quarterly report", "Old report"],
                "items": ["", ""],
                "isXBRL": [1, 1],
                "isInlineXBRL": [1, 0],
            }
        },
    }

    profile, filings = parse_submissions(
        "AAPL",
        payload,
        fetched_at=dt.datetime(2026, 7, 10, tzinfo=dt.UTC),
        today=dt.date(2026, 7, 10),
    )

    assert profile.cik == 320193
    assert profile.sic_description == "Electronic Computers"
    assert [row.form for row in filings] == ["10-Q"]
    assert filings[0].category == "quarterly_report"
    assert filings[0].filing_url.endswith("/aapl-20260328.htm")


def test_8k_item_classification_is_specific() -> None:
    assert filing_category("8-K", "2.02,9.01") == "earnings"
    assert filing_category("8-K", "2.01") == "acquisition"
    assert filing_category("8-K", "5.02") == "leadership"
    assert filing_category("8-K", "8.01") == "current_report"
    assert filing_category("6-K", description="Quarterly earnings results") == "earnings"
    assert filing_category("6-K", description="Change of registered office") == "foreign_report"
    assert filing_category("4") == "insider_ownership"
    assert filing_category("SC 13D/A") == "beneficial_ownership"


def test_company_facts_selects_compact_latest_amended_periods() -> None:
    payload = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {
                                "start": "2026-01-01",
                                "end": "2026-03-31",
                                "val": 100.0,
                                "accn": "0001-26-000001",
                                "fy": 2026,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2026-04-20",
                                "frame": "CY2026Q1",
                            },
                            {
                                "start": "2026-01-01",
                                "end": "2026-03-31",
                                "val": 105.0,
                                "accn": "0001-26-000002",
                                "fy": 2026,
                                "fp": "Q1",
                                "form": "10-Q/A",
                                "filed": "2026-04-25",
                                "frame": "CY2026Q1",
                            },
                            {
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "val": 390.0,
                                "accn": "0001-26-000003",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2026-02-01",
                                "frame": "CY2025",
                            },
                        ]
                    }
                },
                "Assets": {
                    "units": {
                        "USD": [
                            {
                                "end": "2026-03-31",
                                "val": 1000.0,
                                "accn": "0001-26-000002",
                                "fy": 2026,
                                "fp": "Q1",
                                "form": "10-Q/A",
                                "filed": "2026-04-25",
                                "frame": "CY2026Q1I",
                            }
                        ]
                    }
                },
            }
        }
    }

    rows = parse_company_facts("TEST", 1, payload, today=dt.date(2026, 7, 10))
    observations = parse_company_fact_observations("TEST", 1, payload, today=dt.date(2026, 7, 10))
    revenue = [row for row in rows if row.metric == "revenue"]
    assets = [row for row in rows if row.metric == "assets"]

    assert {(row.period_type, row.value) for row in revenue} == {
        ("quarter", 105.0),
        ("annual", 390.0),
    }
    assert assets[0].period_type == "instant"
    assert assets[0].value == 1000.0
    assert revenue[0].source_url.startswith("https://www.sec.gov/Archives/edgar/data/1/")
    assert {row.accession_number for row in observations if row.metric == "revenue"} == {
        "0001-26-000001",
        "0001-26-000002",
        "0001-26-000003",
    }


def test_company_facts_derives_only_adjacent_additive_ytd_quarters() -> None:
    payload = {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "start": "2026-01-01",
                                "end": "2026-03-31",
                                "val": 10.0,
                                "accn": "0001-26-000001",
                                "form": "10-Q",
                                "filed": "2026-04-20",
                            },
                            {
                                "start": "2026-01-01",
                                "end": "2026-06-30",
                                "val": 25.0,
                                "accn": "0001-26-000002",
                                "form": "10-Q",
                                "filed": "2026-07-20",
                            },
                            {
                                "start": "2026-01-01",
                                "end": "2026-09-30",
                                "val": 45.0,
                                "accn": "0001-26-000003",
                                "form": "10-Q",
                                "filed": "2026-10-20",
                            },
                        ]
                    }
                }
            }
        }
    }

    rows = parse_company_facts("TEST", 1, payload, today=dt.date(2026, 10, 21))

    assert [(row.period_end, row.value, row.period_type) for row in rows] == [
        (dt.date(2026, 3, 31), 10.0, "quarter"),
        (dt.date(2026, 6, 30), 15.0, "quarter"),
        (dt.date(2026, 9, 30), 20.0, "quarter"),
    ]
    assert rows[-1].frame == "derived:2026-06-30"


def test_company_facts_does_not_subtract_ytd_eps_or_skip_a_missing_period() -> None:
    payload = {
        "facts": {
            "us-gaap": {
                "EarningsPerShareDiluted": {
                    "units": {
                        "USD/shares": [
                            {
                                "start": "2026-01-01",
                                "end": "2026-03-31",
                                "val": 1.0,
                                "accn": "0001-26-000001",
                                "form": "10-Q",
                                "filed": "2026-04-20",
                            },
                            {
                                "start": "2026-01-01",
                                "end": "2026-06-30",
                                "val": 2.5,
                                "accn": "0001-26-000002",
                                "form": "10-Q",
                                "filed": "2026-07-20",
                            },
                        ]
                    }
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            {
                                "start": "2026-01-01",
                                "end": "2026-09-30",
                                "val": 45.0,
                                "accn": "0001-26-000003",
                                "form": "10-Q",
                                "filed": "2026-10-20",
                            }
                        ]
                    }
                },
            }
        }
    }

    rows = parse_company_facts("TEST", 1, payload, today=dt.date(2026, 10, 21))

    assert [(row.metric, row.period_end, row.value) for row in rows] == [
        ("eps_diluted", dt.date(2026, 3, 31), 1.0)
    ]


def test_company_facts_rejects_periods_after_filing_or_collection_date() -> None:
    payload = {
        "facts": {
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {
                                "end": "2034-03-05",
                                "val": 999_999,
                                "accn": "0001-24-000001",
                                "fy": 2023,
                                "fp": "FY",
                                "form": "10-K/A",
                                "filed": "2024-03-27",
                            },
                            {
                                "end": "2026-03-31",
                                "val": 100_000,
                                "accn": "0001-26-000001",
                                "fy": 2026,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2026-04-20",
                            },
                            {
                                "end": "2026-08-01",
                                "val": 110_000,
                                "accn": "0001-26-000002",
                                "fy": 2026,
                                "fp": "Q2",
                                "form": "10-Q",
                                "filed": "2026-08-10",
                            },
                        ]
                    }
                }
            }
        }
    }

    rows = parse_company_facts("TEST", 1, payload, today=dt.date(2026, 7, 18))

    assert [(row.period_end, row.value) for row in rows] == [(dt.date(2026, 3, 31), 100_000.0)]
