from __future__ import annotations

import datetime as dt

import pytest

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


def test_token_signature_matching_handles_real_sec_and_vendor_names() -> None:
    symbols = [
        SymbolIdentity(code="BA", name="Boeing Company (The)"),
        SymbolIdentity(
            code="BABA",
            name="Alibaba Group Holding Limited ADS each representing eight Ordinary Shares",
        ),
        SymbolIdentity(
            code="DIA",
            name="State Street SPDR Dow Jones Industrial Average ETF Trust",
        ),
        SymbolIdentity(code="HD", name="Home Depot Inc (The)"),
        SymbolIdentity(code="IWM", name="iShares Russell 2000 Index Fund"),
        SymbolIdentity(code="LLY", name="Eli Lilly and Company"),
        SymbolIdentity(code="MCD", name="McDonald's Corporation"),
        SymbolIdentity(code="SPY", name="State Street SPDR S&P 500 ETF Trust"),
        SymbolIdentity(code="TLT", name="iShares 20+ Year Treasury Bond ETF"),
        SymbolIdentity(code="UNH", name="UnitedHealth Group Incorporated (DE)"),
        SymbolIdentity(code="XOM", name="ExxonMobil Holdings Corporation"),
    ]
    cases = [
        ("BOEING CO", "COM", "BA"),
        ("ALIBABA GROUP HLDG LTD", "SPONSORED ADS", "BABA"),
        ("SPDR DOW JONES INDL AVERAGE ETF TR", "UNIT SER 1", "DIA"),
        ("HOME DEPOT INC", "COM", "HD"),
        ("ISHARES TR", "RUSSELL 2000 ETF", "IWM"),
        ("LILLY ELI & CO", "COM", "LLY"),
        ("MCDONALDS CORP", "COM", "MCD"),
        ("SPDR S&P 500 ETF TR", "TR UNIT", "SPY"),
        ("ISHARES TR", "20+ YR TREAS BD ETF", "TLT"),
        ("UNITEDHEALTH GROUP INC", "COM", "UNH"),
        ("EXXON MOBIL CORP", "COM", "XOM"),
    ]

    for issuer, title, expected_code in cases:
        match = match_13f_security(issuer, title, symbols)
        assert match is not None
        assert match[0] == expected_code
        assert match[1] >= 0.99


def test_token_signature_matching_rejects_ambiguous_share_classes() -> None:
    symbols = [
        SymbolIdentity(code="FOOA", name="Foo Holdings Class A Common Stock"),
        SymbolIdentity(code="FOOC", name="Foo Holdings Class C Common Stock"),
    ]

    assert match_13f_security("FOO HLDGS", "COM", symbols) is None


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


def test_aggregate_change_is_not_inflated_by_manager_cik_migration() -> None:
    prior_date = dt.date(2025, 12, 31)
    current_date = dt.date(2026, 3, 31)
    prior = ArchiveResult(
        source_url="https://www.sec.gov/prior.zip",
        report_date=prior_date,
        positions=(_position("AAPL", 1, 100, 1000, prior_date),),
        matches=(),
        unmatched_cusips=0,
        manager_filings={1: _filing(1, prior_date)},
    )
    current = ArchiveResult(
        source_url="https://www.sec.gov/current.zip",
        report_date=current_date,
        positions=(_position("AAPL", 2, 100, 1200, current_date),),
        matches=(),
        unmatched_cusips=0,
        manager_filings={2: _filing(2, current_date)},
    )

    positions, summaries = build_holding_changes(current, prior)

    assert [row.change_type for row in positions] == ["new"]
    assert summaries[0].net_share_change == 0
    assert summaries[0].net_change_pct == 0


def test_watched_manager_survives_bounded_position_retention() -> None:
    prior_date = dt.date(2025, 12, 31)
    current_date = dt.date(2026, 3, 31)
    regular_managers = list(range(1, 161))
    watched_manager = 999
    managers = [*regular_managers, watched_manager]
    prior = ArchiveResult(
        source_url="https://www.sec.gov/prior.zip",
        report_date=prior_date,
        positions=tuple(
            _position("TEST", manager, 100, 10_000 - manager, prior_date)
            for manager in managers
        ),
        matches=(),
        unmatched_cusips=0,
        manager_filings={manager: _filing(manager, prior_date) for manager in managers},
    )
    current = ArchiveResult(
        source_url="https://www.sec.gov/current.zip",
        report_date=current_date,
        positions=tuple(
            _position(
                "TEST",
                manager,
                100,
                1 if manager == watched_manager else 10_000 - manager,
                current_date,
            )
            for manager in managers
        ),
        matches=(),
        unmatched_cusips=0,
        manager_filings={manager: _filing(manager, current_date) for manager in managers},
    )

    without_watch, _ = build_holding_changes(current, prior)
    with_watch, _ = build_holding_changes(
        current,
        prior,
        watched_manager_ciks=frozenset({watched_manager}),
    )

    assert watched_manager not in {row.manager_cik for row in without_watch}
    assert watched_manager in {row.manager_cik for row in with_watch}
    assert len(with_watch) <= 150


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


def test_archive_reports_bounded_streaming_progress(tmp_path) -> None:
    import zipfile

    archive_path = tmp_path / "13f-progress.zip"
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
            "0000000001-26-000001\tUNKNOWN ONE\tCOM\t000000001\t1\t1\tSH\t\n"
            "0000000001-26-000001\tUNKNOWN TWO\tCOM\t000000002\t1\t1\tSH\t\n"
            "0000000001-26-000001\tAPPLE INC\tCOM\t037833100\t2\t2\tSH\t\n"
        ),
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)

    progress: list[int] = []
    result = parse_13f_archive(
        archive_path,
        source_url="https://www.sec.gov/example.zip",
        symbols=[SymbolIdentity(code="AAPL", name="Apple Inc. - Common Stock")],
        progress=progress.append,
        progress_every_rows=2,
    )

    assert progress == [2]
    assert result.unmatched_cusips == 2
    assert [(row.code, row.shares) for row in result.positions] == [("AAPL", 2)]


def test_archive_rejects_non_positive_progress_interval(tmp_path) -> None:
    with pytest.raises(ValueError, match="progress_every_rows must be positive"):
        parse_13f_archive(
            tmp_path / "unused.zip",
            source_url="https://www.sec.gov/example.zip",
            symbols=[],
            progress_every_rows=0,
        )


def test_archive_replays_earlier_rows_when_same_cusip_has_a_later_exact_label(
    tmp_path,
) -> None:
    import zipfile

    archive_path = tmp_path / "13f-label-variant.zip"
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
            "0000000001-26-000001\tISHARES 20 YEAR TREASURY BD\tFUND\t\t999"
            "\t999\tSH\t\n"
            "0000000001-26-000001\tISHARES TR\t20 YR TR BD ETF\t464287432\t100"
            "\t10\tSH\t\n"
            "0000000001-26-000001\tISHARES 20 YEAR TREASURY BD\tFUND\t464287432"
            "\t200\t20\tSH\t\n"
        ),
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)

    result = parse_13f_archive(
        archive_path,
        source_url="https://www.sec.gov/example.zip",
        symbols=[SymbolIdentity(code="TLT", name="iShares 20+ Year Treasury Bond ETF")],
    )

    assert result.unmatched_cusips == 0
    assert [(row.code, row.shares, row.value_usd) for row in result.positions] == [
        ("TLT", 30, 300)
    ]
    assert result.matches[0].match_method == "exact_normalized_issuer"
