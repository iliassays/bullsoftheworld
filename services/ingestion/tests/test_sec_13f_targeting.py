from __future__ import annotations

import datetime as dt
from dataclasses import replace

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
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/"
            "0000000001-26-000001-index.html"
        ),
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

    path = sec_13f._archive_cache_path(tmp_path, source_url, fingerprint)
    writer = sec_13f._ArchiveCacheWriter(path)
    writer.add(archive.positions[0])
    metadata_archive = replace(archive, positions=())
    writer.finish(metadata_archive, fingerprint=fingerprint)
    loaded = sec_13f._load_archive_cache(
        tmp_path,
        source_url,
        fingerprint=fingerprint,
    )

    assert path.stat().st_mode & 0o777 == 0o600
    assert loaded is not None
    restored, restored_path = loaded
    assert restored_path == path
    assert restored == metadata_archive
    connection = sec_13f.sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        assert sec_13f._positions_from_cache(connection, "NXTC", restored) == archive.positions
    finally:
        connection.close()
    assert (
        sec_13f._load_archive_cache(
            tmp_path,
            source_url,
            fingerprint="different-scope",
        )
        is None
    )


@pytest.mark.asyncio
async def test_disk_backed_quarter_comparison_preserves_change_semantics(
    tmp_path, monkeypatch
) -> None:
    source_url = "https://www.sec.gov/files/form13f.zip"

    def archive(report_date: dt.date, shares: int, value: float, suffix: str):
        accession = f"0000000001-26-0000{suffix}"
        filing = ManagerFiling(
            cik=1,
            name="Example Capital",
            report_date=report_date,
            filing_date=report_date + dt.timedelta(days=45),
            accession_number=accession,
            source_url=(
                f"https://www.sec.gov/Archives/edgar/data/1/{accession.replace('-', '')}/"
                f"{accession}-index.html"
            ),
        )
        position = RawInstitutionalPosition(
            code="NXTC",
            cusip="000000001",
            manager_cik=1,
            manager_name=filing.name,
            report_date=report_date,
            filing_date=filing.filing_date,
            accession_number=accession,
            shares=shares,
            value_usd=value,
            source_url=filing.source_url,
        )
        return (
            ArchiveResult(
                source_url=f"{source_url}?{suffix}",
                report_date=report_date,
                positions=(),
                matches=(),
                unmatched_cusips=0,
                manager_filings={1: filing},
            ),
            position,
        )

    prior, prior_position = archive(dt.date(2025, 12, 31), 100, 500.0, "01")
    current, current_position = archive(dt.date(2026, 3, 31), 150, 800.0, "02")
    prior_path = tmp_path / "prior.sqlite3"
    current_path = tmp_path / "current.sqlite3"
    for metadata, position, path in (
        (prior, prior_position, prior_path),
        (current, current_position, current_path),
    ):
        writer = sec_13f._ArchiveCacheWriter(path)
        writer.add(position)
        writer.finish(metadata, fingerprint="test")

    captured = {}

    async def fake_persist(metadata, changes, summaries, *, codes):
        captured.update(changes=changes, summaries=summaries, codes=codes)
        return {
            "positions": len(changes),
            "summaries": len(summaries),
            "identifiers": 0,
            "managers": len(changes),
        }

    monkeypatch.setattr(sec_13f, "_persist_period", fake_persist)

    stats, summaries = await sec_13f._persist_cached_period(
        current,
        current_path,
        prior,
        prior_path,
        symbols=[SymbolIdentity(code="NXTC", name="NextCure, Inc.")],
    )

    assert stats["positions"] == 1
    assert captured["codes"] == ["NXTC"]
    assert captured["changes"][0].change_type == "increased"
    assert captured["changes"][0].share_change == 50
    assert summaries[0].net_share_change == 50
    assert summaries[0].net_change_pct == 50.0
