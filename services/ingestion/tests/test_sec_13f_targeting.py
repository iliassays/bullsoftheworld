from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.dialects import postgresql

from bulls.market_data.providers.sec_13f import (
    ArchiveResult,
    CusipMatch,
    ManagerFiling,
    RawInstitutionalPosition,
    SymbolIdentity,
)
from ingestion import sec_13f


def test_target_codes_are_normalized_and_deduplicated() -> None:
    assert sec_13f._normalize_codes(" nxtc,AGEN,NXTC, ") == ["AGEN", "NXTC"]
    assert sec_13f._normalize_codes(None) is None


def test_selected_archive_window_is_validated_and_processed_oldest_first() -> None:
    assert sec_13f._selected_archive_urls(["newest", "prior", "baseline", "older"], 2) == [
        "baseline",
        "prior",
        "newest",
    ]
    with pytest.raises(RuntimeError, match="3 required"):
        sec_13f._selected_archive_urls(["newest", "prior"], 2)


def test_target_cli_keeps_codes_explicit() -> None:
    args = sec_13f._args(["--history-quarters", "8", "--force", "--codes", "NXTC,AGEN"])

    assert args.history_quarters == 8
    assert args.force is True
    assert args.codes == "NXTC,AGEN"


def test_target_period_delete_is_symbol_scoped() -> None:
    position_delete, summary_delete = sec_13f._period_deletes(
        dt.date(2026, 3, 31), ["AGEN", "NXTC"]
    )
    position_sql = str(
        position_delete.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    summary_sql = str(
        summary_delete.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "institutional_positions.code IN ('AGEN', 'NXTC')" in position_sql
    assert "institutional_holding_summaries.code IN ('AGEN', 'NXTC')" in summary_sql


def test_derived_archive_cache_round_trips_with_mapping_provenance(tmp_path) -> None:
    source_url = "https://www.sec.gov/files/form13f.zip"
    filing = ManagerFiling(
        cik=1,
        name="Example Capital",
        report_date=dt.date(2026, 3, 31),
        filing_date=dt.date(2026, 5, 15),
        accession_number="0000000001-26-000001",
        source_url="https://www.sec.gov/Archives/example",
    )
    archive = ArchiveResult(
        source_url=source_url,
        report_date=filing.report_date,
        positions=(
            RawInstitutionalPosition(
                code="NXTC",
                cusip="000000001",
                manager_cik=filing.cik,
                manager_name=filing.name,
                report_date=filing.report_date,
                filing_date=filing.filing_date,
                accession_number=filing.accession_number,
                shares=100,
                value_usd=500.0,
                source_url=filing.source_url,
            ),
        ),
        matches=(
            CusipMatch(
                code="NXTC",
                cusip="000000001",
                issuer_name="NEXTCURE INC",
                title_of_class="COM",
                confidence=1.0,
                match_method="exact_normalized_issuer",
            ),
        ),
        unmatched_cusips=2,
        manager_filings={filing.cik: filing},
    )
    fingerprint = sec_13f._mapping_fingerprint([SymbolIdentity(code="NXTC", name="NextCure, Inc.")])

    path = sec_13f._store_archive_cache(
        tmp_path,
        archive,
        fingerprint=fingerprint,
    )
    restored = sec_13f._load_archive_cache(
        tmp_path,
        source_url,
        fingerprint=fingerprint,
    )

    assert path.stat().st_mode & 0o777 == 0o600
    assert restored == archive
    assert (
        sec_13f._load_archive_cache(
            tmp_path,
            source_url,
            fingerprint="different-scope",
        )
        is None
    )
