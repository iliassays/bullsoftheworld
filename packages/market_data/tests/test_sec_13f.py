from __future__ import annotations

import datetime as dt

from bulls.market_data.providers.sec_13f import (
    ArchiveResult,
    ManagerFiling,
    RawInstitutionalPosition,
    SymbolIdentity,
    build_holding_changes,
    discover_dataset_urls,
    match_13f_security,
    parse_13f_archive,
)


def test_dataset_links_preserve_sec_page_order() -> None:
    html = """
    <a href="/files/structureddata/data/form-13f-data-sets/current_form13f.zip">Current</a>
    <a href="/files/structureddata/data/form-13f-data-sets/prior_form13f.zip">Prior</a>
    """
    assert discover_dataset_urls(html) == [
        "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/current_form13f.zip",
        "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/prior_form13f.zip",
    ]


def test_strict_issuer_matching_handles_share_classes_without_guessing() -> None:
    symbols = [
        SymbolIdentity(code="GOOG", name="Alphabet Inc. - Class C Capital Stock"),
        SymbolIdentity(code="GOOGL", name="Alphabet Inc. - Class A Common Stock"),
        SymbolIdentity(code="AAPL", name="Apple Inc. - Common Stock"),
    ]
    assert match_13f_security("APPLE INC", "COM", symbols) == (
        "AAPL",
        1.0,
        "exact_normalized_issuer",
    )
    assert match_13f_security("ALPHABET INC", "CAP STK CL A", symbols) == (
        "GOOGL",
        1.0,
        "exact_issuer_and_class",
    )
    assert match_13f_security("ALPHABET INC", "CAP STK", symbols) is None


def test_strict_issuer_matching_handles_common_etf_legal_designators() -> None:
    symbols = [
        SymbolIdentity(code="SPY", name="SPDR S&P 500 ETF Trust"),
        SymbolIdentity(code="QQQ", name="Invesco QQQ Trust, Series 1"),
    ]

    assert match_13f_security("SPDR S&P 500 ETF TR", "UNIT", symbols) == (
        "SPY",
        1.0,
        "exact_normalized_issuer",
    )
    assert match_13f_security("INVESCO QQQ TR", "UNIT SER 1", symbols) == (
        "QQQ",
        1.0,
        "exact_normalized_issuer",
    )


def _position(
    code: str,
    manager: int,
    shares: int,
    value: float,
    report: dt.date,
) -> RawInstitutionalPosition:
    return RawInstitutionalPosition(
        code=code,
        cusip="037833100",
        manager_cik=manager,
        manager_name=f"Manager {manager}",
        report_date=report,
        filing_date=report + dt.timedelta(days=40),
        accession_number=f"{manager:010d}-26-000001",
        shares=shares,
        value_usd=value,
        source_url="https://www.sec.gov/example",
    )


def _filing(manager: int, report: dt.date) -> ManagerFiling:
    return ManagerFiling(
        cik=manager,
        name=f"Manager {manager}",
        report_date=report,
        filing_date=report + dt.timedelta(days=40),
        accession_number=f"{manager:010d}-26-000001",
        source_url="https://www.sec.gov/example",
    )


def test_holding_changes_include_entries_reductions_and_exits() -> None:
    prior_date = dt.date(2025, 12, 31)
    current_date = dt.date(2026, 3, 31)
    prior = ArchiveResult(
        source_url="https://www.sec.gov/prior.zip",
        report_date=prior_date,
        positions=(
            _position("AAPL", 1, 100, 1000, prior_date),
            _position("AAPL", 2, 50, 500, prior_date),
        ),
        matches=(),
        unmatched_cusips=0,
        manager_filings={1: _filing(1, prior_date), 2: _filing(2, prior_date)},
    )
    current = ArchiveResult(
        source_url="https://www.sec.gov/current.zip",
        report_date=current_date,
        positions=(
            _position("AAPL", 1, 150, 1800, current_date),
            _position("AAPL", 3, 25, 300, current_date),
        ),
        matches=(),
        unmatched_cusips=0,
        manager_filings={
            1: _filing(1, current_date),
            2: _filing(2, current_date),
            3: _filing(3, current_date),
        },
    )

    positions, summaries = build_holding_changes(
        current, prior, now=dt.datetime(2026, 5, 20, tzinfo=dt.UTC)
    )

    assert {row.manager_cik: row.change_type for row in positions} == {
        1: "increased",
        2: "exited",
        3: "new",
    }
    summary = summaries[0]
    assert summary.total_shares == 175
    assert summary.net_share_change == 25
    assert summary.new_positions == 1
    assert summary.increased_positions == 1
    assert summary.exited_positions == 1


def test_missing_current_manager_filing_is_not_called_an_exit() -> None:
    prior_date = dt.date(2025, 12, 31)
    current_date = dt.date(2026, 3, 31)
    prior = ArchiveResult(
        source_url="https://www.sec.gov/prior.zip",
        report_date=prior_date,
        positions=(_position("AAPL", 2, 50, 500, prior_date),),
        matches=(),
        unmatched_cusips=0,
        manager_filings={2: _filing(2, prior_date)},
    )
    current = ArchiveResult(
        source_url="https://www.sec.gov/current.zip",
        report_date=current_date,
        positions=(),
        matches=(),
        unmatched_cusips=0,
        manager_filings={},
    )

    positions, summaries = build_holding_changes(current, prior)

    assert positions == []
    assert summaries == []


def test_archive_value_is_already_reported_in_us_dollars(tmp_path) -> None:
    import zipfile

    archive_path = tmp_path / "13f.zip"
    files = {
        "COVERPAGE.tsv": (
            "ACCESSION_NUMBER\tFILINGMANAGER_NAME\n"
            "0000000001-26-000001\tExample Manager\n"
        ),
        "SUBMISSION.tsv": (
            "ACCESSION_NUMBER\tCIK\tFILING_DATE\tPERIODOFREPORT\tSUBMISSIONTYPE\n"
            "0000000001-26-000001\t1\t15-May-2026\t31-Mar-2026\t13F-HR\n"
        ),
        "INFOTABLE.tsv": (
            "ACCESSION_NUMBER\tNAMEOFISSUER\tTITLEOFCLASS\tCUSIP\tVALUE\tSSHPRNAMT"
            "\tSSHPRNAMTTYPE\tPUTCALL\n"
            "0000000001-26-000001\tAPPLE INC\tCOM\t037833100\t290512251859"
            "\t1144695425\tSH\t\n"
        ),
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)

    result = parse_13f_archive(
        archive_path,
        source_url="https://www.sec.gov/example.zip",
        symbols=[SymbolIdentity(code="AAPL", name="Apple Inc. - Common Stock")],
    )

    assert result.positions[0].value_usd == 290_512_251_859
