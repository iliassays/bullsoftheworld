"""US security-master publish rules.

These tests stay DB-free: the important contract is that raw noisy instruments remain in the
security master while only product-eligible securities are projected into `symbols`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from bulls.market_data.providers.us_security_master import parse_nasdaq_listed, parse_other_listed
from ingestion.security_master import (
    MINIMUM_RECORDS_PER_LISTING_FILE,
    _chunks,
    _symbol_rows,
    identity_continuity_conflicts,
    security_id_backlink_stmt,
    validate_security_master_snapshot,
)


def test_symbol_rows_publish_only_product_eligible_instruments() -> None:
    records = parse_nasdaq_listed(
        """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAPL|Apple Inc. - Common Stock|Q|N|N|40|N|N
AACIW|Armada Acquisition Corp. III - Warrant|G|N|N|100|N|N
TEST|Nasdaq Test Company - Common Stock|S|Y|N|100|N|N
"""
    ) + parse_other_listed(
        """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
BRK.B|Berkshire Hathaway Inc. Class B Common Stock|N|BRK.B|N|100|N|BRK-B
ABR$D|Arbor Realty Trust Preferred Stock|N|ABRpD|N|100|N|ABR-D
"""
    )

    rows = _symbol_rows(records)

    assert [row["code"] for row in rows] == ["AAPL", "BRK-B"]
    assert all(row["market"] == "US" for row in rows)
    assert all(row["is_active"] is True for row in rows)
    assert all(row["is_hidden"] is False for row in rows)


def test_symbol_rows_preserve_long_official_names() -> None:
    long_name = "Example Holdings " + "International " * 12 + "Common Stock"
    records = parse_nasdaq_listed(
        "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
        f"LONG|{long_name}|Q|N|N|100|N|N\n"
    )

    [row] = _symbol_rows(records)

    assert len(long_name) > 160
    assert row["name_en"] == long_name


def test_security_id_backlink_is_a_join_update_guarded_by_change() -> None:
    sql = str(
        security_id_backlink_stmt("US").compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )

    # A join-style UPDATE evaluates the security-master lookup once per matched row instead of
    # re-running a correlated subquery for every symbol row.
    assert "FROM security_master" in sql
    assert "SELECT" not in sql.upper()
    # Unchanged rows must be skipped so repeated refreshes stay within the statement timeout.
    assert "IS DISTINCT FROM" in sql


def test_bulk_rows_are_chunked_before_upsert() -> None:
    rows = list(range(2501))

    chunks = _chunks(rows, size=1000)

    assert [len(chunk) for chunk in chunks] == [1000, 1000, 501]
    assert chunks[0][0] == 0
    assert chunks[-1][-1] == 2500


def _valid_snapshot_records():
    nasdaq = parse_nasdaq_listed(
        "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
        + "\n".join(
            f"N{i:04d}|Nasdaq {i} Common Stock|Q|N|N|100|N|N"
            for i in range(MINIMUM_RECORDS_PER_LISTING_FILE)
        )
        + "\n"
    )
    other = parse_other_listed(
        "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\n"
        + "\n".join(
            f"O{i:04d}|Other {i} Common Stock|N|O{i:04d}|N|100|N|O{i:04d}"
            for i in range(MINIMUM_RECORDS_PER_LISTING_FILE)
        )
        + "\n"
    )
    return [
        record.model_copy(update={"cik": index + 1}) for index, record in enumerate(nasdaq + other)
    ]


def test_security_master_snapshot_guard_accepts_complete_sources() -> None:
    quality = validate_security_master_snapshot(_valid_snapshot_records())

    assert quality.records == MINIMUM_RECORDS_PER_LISTING_FILE * 2
    assert quality.cik_coverage_ratio == 1.0
    assert quality.records_by_source_file == {
        "nasdaqlisted": MINIMUM_RECORDS_PER_LISTING_FILE,
        "otherlisted": MINIMUM_RECORDS_PER_LISTING_FILE,
    }


def test_security_master_snapshot_guard_rejects_partial_source() -> None:
    records = _valid_snapshot_records()

    with pytest.raises(ValueError, match="otherlisted snapshot is incomplete"):
        validate_security_master_snapshot(
            [record for record in records if record.source_file == "nasdaqlisted"]
        )


def test_security_master_snapshot_guard_rejects_coverage_collapse() -> None:
    with pytest.raises(ValueError, match="active coverage collapsed"):
        validate_security_master_snapshot(
            _valid_snapshot_records(),
            previous_active_count=2_000,
        )


def test_security_master_snapshot_guard_rejects_missing_sec_identity() -> None:
    records = [record.model_copy(update={"cik": None}) for record in _valid_snapshot_records()]

    with pytest.raises(ValueError, match="SEC identity coverage is incomplete"):
        validate_security_master_snapshot(records)


def test_security_master_rejects_silent_symbol_reuse() -> None:
    [record] = parse_nasdaq_listed(
        "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
        "REUSE|New Issuer Common Stock|Q|N|N|100|N|N\n"
    )
    record = record.model_copy(update={"cik": 222})

    assert identity_continuity_conflicts({"REUSE": SimpleNamespace(cik=111)}, [record]) == [
        "REUSE:111->222"
    ]


def test_security_master_allows_missing_to_verified_cik_enrichment() -> None:
    [record] = parse_nasdaq_listed(
        "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
        "KNOWN|Known Issuer Common Stock|Q|N|N|100|N|N\n"
    )
    record = record.model_copy(update={"cik": 222})

    assert identity_continuity_conflicts({"KNOWN": SimpleNamespace(cik=None)}, [record]) == []
