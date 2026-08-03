"""Streaming parser for the SEC's official quarterly Form 13F data sets.

Only long share positions that map confidently to the supported symbol universe are retained.
Options, principal amounts, unresolved CUSIPs, and the large raw archive are excluded from product
data. A 13F reveals quarter-end holdings after a filing delay; it does not reveal trade dates.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import math
import re
import zipfile
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

from pydantic import BaseModel

from bulls.market_data.providers.sec_edgar import filing_index_url

DATASET_PAGE = "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
MAX_STORED_MANAGERS_PER_SYMBOL = 150
TOP_BY_VALUE = 100
TOP_BY_CHANGE = 25
MAX_LABEL_ATTEMPTS_PER_CUSIP = 8


class SymbolIdentity(BaseModel):
    code: str
    name: str


class CusipMatch(BaseModel):
    code: str
    cusip: str
    issuer_name: str
    title_of_class: str
    confidence: float
    match_method: str


class RawInstitutionalPosition(BaseModel):
    code: str
    cusip: str
    manager_cik: int
    manager_name: str
    report_date: dt.date
    filing_date: dt.date
    accession_number: str
    shares: int
    value_usd: float
    source_url: str


class InstitutionalPositionChange(BaseModel):
    market: str = "US"
    code: str
    report_date: dt.date
    manager_cik: int
    manager_name: str
    cusip: str
    shares: int
    value_usd: float
    prior_shares: int | None
    share_change: int | None
    change_pct: float | None
    change_type: str
    filing_date: dt.date
    accession_number: str
    source_url: str
    value_rank: int


class InstitutionalSummary(BaseModel):
    market: str = "US"
    code: str
    report_date: dt.date
    prior_report_date: dt.date | None
    latest_filing_date: dt.date
    managers_count: int
    total_shares: int
    total_value_usd: float
    new_positions: int
    increased_positions: int
    reduced_positions: int
    exited_positions: int
    unchanged_positions: int
    net_share_change: int | None
    net_change_pct: float | None
    share_basis_comparable: bool | None
    source_url: str
    updated_at: dt.datetime


@dataclass(frozen=True)
class ArchiveResult:
    source_url: str
    report_date: dt.date
    positions: tuple[RawInstitutionalPosition, ...]
    matches: tuple[CusipMatch, ...]
    unmatched_cusips: int
    manager_filings: dict[int, ManagerFiling]


@dataclass(frozen=True)
class ManagerFiling:
    cik: int
    name: str
    report_date: dt.date
    filing_date: dt.date
    accession_number: str
    source_url: str


class _ZipLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href and href.lower().endswith(".zip") and "form13f" in href.lower():
            self.links.append(href)


def discover_dataset_urls(html: str, *, base_url: str = DATASET_PAGE) -> list[str]:
    parser = _ZipLinkParser()
    parser.feed(html)
    return list(dict.fromkeys(urljoin(base_url, href) for href in parser.links))


_INSTRUMENT_WORDS = re.compile(
    r"\b(COM|COMMON|ORDINARY|CAPITAL|STOCK|SHARES?|AMERICAN|DEPOSITARY|DEPOSITORY|"
    r"ADS|ADR|ETF|FUND|INDEX|SPONSORED|TRUST|TR|UNIT|SERIES|SER|NEW|DEL)\b"
)
_CLASS_WORDS = re.compile(r"\b(?:CLASS|CL)\s*([A-Z])\b")
_SERIES_WORDS = re.compile(r"\b(?:SERIES|SER)\s*\d+\b")
_NON_ALNUM = re.compile(r"[^A-Z0-9]+")
_VALID_CUSIP = re.compile(r"[A-Z0-9]{9}")
_LEGAL_WORDS = re.compile(
    r"\b(AND|CO|CORP|INC|LTD|LLC|PLC|LP|L P|THE|DE|HOLDING|HOLDINGS|HLDG|HLDGS)\b"
)
_TOKEN_ALIASES = {
    "BD": "BOND",
    "INDL": "INDUSTRIAL",
    "MCDONALD": "MCDONALDS",
    "TREAS": "TREASURY",
    "YR": "YEAR",
}


def _class_token(text: str) -> str | None:
    match = _CLASS_WORDS.search(text.upper())
    return match.group(1) if match else None


def normalize_issuer_name(value: str) -> str:
    text = re.sub(r"([A-Z])['\u2019]S\b", r"\1S", value.upper())
    text = text.replace("EXXONMOBIL", "EXXON MOBIL")
    text = text.replace("J P MORGAN", "JPMORGAN").replace("JP MORGAN", "JPMORGAN")
    text = text.replace("CORPORATION", "CORP").replace("INCORPORATED", "INC")
    text = text.replace("COMPANY", "CO").replace("LIMITED", "LTD")
    text = re.sub(r"\bEACH\s+REPRESENTING\b.*$", " ", text)
    if "SPDR" in text:
        text = re.sub(r"\bSTATE\s+STREET\b", " ", text)
    text = _CLASS_WORDS.sub(" ", text)
    text = _SERIES_WORDS.sub(" ", text)
    text = _INSTRUMENT_WORDS.sub(" ", text)
    text = _LEGAL_WORDS.sub(" ", text)
    tokens = [_TOKEN_ALIASES.get(token, token) for token in _NON_ALNUM.sub(" ", text).split()]
    return " ".join(tokens)


def _identity_signature(value: str) -> tuple[str, ...]:
    """Return an order-independent exact signature after conservative SEC-name normalization."""
    return tuple(sorted(set(normalize_issuer_name(value).split())))


@dataclass(frozen=True)
class _SymbolMatchIndex:
    by_issuer: dict[str, tuple[SymbolIdentity, ...]]
    by_signature: dict[tuple[str, ...], tuple[SymbolIdentity, ...]]


def _symbol_match_index(symbols: Iterable[SymbolIdentity]) -> _SymbolMatchIndex:
    by_issuer: dict[str, list[SymbolIdentity]] = defaultdict(list)
    by_signature: dict[tuple[str, ...], list[SymbolIdentity]] = defaultdict(list)
    for symbol in symbols:
        by_issuer[normalize_issuer_name(symbol.name)].append(symbol)
        by_signature[_identity_signature(symbol.name)].append(symbol)
    return _SymbolMatchIndex(
        by_issuer={key: tuple(value) for key, value in by_issuer.items()},
        by_signature={key: tuple(value) for key, value in by_signature.items()},
    )


def _match_13f_security(
    issuer_name: str,
    title_of_class: str,
    index: _SymbolMatchIndex,
) -> tuple[str, float, str] | None:
    issuer_key = normalize_issuer_name(issuer_name)
    candidates = index.by_issuer.get(issuer_key, ())
    if len(candidates) == 1:
        return candidates[0].code, 1.0, "exact_normalized_issuer"
    if len(candidates) > 1:
        filing_class = _class_token(title_of_class)
        if filing_class:
            class_matches = [
                symbol for symbol in candidates if _class_token(symbol.name) == filing_class
            ]
            if len(class_matches) == 1:
                return class_matches[0].code, 1.0, "exact_issuer_and_class"

    filing_signature = _identity_signature(f"{issuer_name} {title_of_class}")
    if not filing_signature:
        return None
    signature_candidates = index.by_signature.get(filing_signature, ())
    if len(signature_candidates) == 1:
        return signature_candidates[0].code, 0.99, "exact_normalized_token_signature"
    if len(signature_candidates) > 1:
        filing_class = _class_token(title_of_class)
        if filing_class:
            class_matches = [
                symbol
                for symbol in signature_candidates
                if _class_token(symbol.name) == filing_class
            ]
            if len(class_matches) == 1:
                return class_matches[0].code, 0.99, "exact_token_signature_and_class"
    return None


def match_13f_security(
    issuer_name: str,
    title_of_class: str,
    symbols: Iterable[SymbolIdentity],
) -> tuple[str, float, str] | None:
    return _match_13f_security(
        issuer_name,
        title_of_class,
        _symbol_match_index(symbols),
    )


def _member_name(archive: zipfile.ZipFile, expected: str) -> str:
    matches = [name for name in archive.namelist() if Path(name).name.upper() == expected.upper()]
    if len(matches) != 1:
        raise ValueError(f"13F archive must contain exactly one {expected}; found {len(matches)}")
    return matches[0]


def _rows(archive: zipfile.ZipFile, expected: str):
    member = _member_name(archive, expected)
    with (
        archive.open(member) as raw,
        io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="") as text,
    ):
        yield from csv.DictReader(text, delimiter="\t")


def _parse_date(value: str | None) -> dt.date:
    raw = (value or "").strip()
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"invalid SEC 13F date {value!r}")


@dataclass(frozen=True)
class _Submission:
    accession: str
    cik: int
    filing_date: dt.date
    report_date: dt.date
    submission_type: str
    manager_name: str
    amendment_type: str | None


def _selected_submissions(archive: zipfile.ZipFile) -> dict[str, _Submission]:
    cover = {row["ACCESSION_NUMBER"]: row for row in _rows(archive, "COVERPAGE.tsv")}
    grouped: dict[tuple[int, dt.date], list[_Submission]] = defaultdict(list)
    for row in _rows(archive, "SUBMISSION.tsv"):
        submission_type = (row.get("SUBMISSIONTYPE") or "").strip()
        if submission_type not in {"13F-HR", "13F-HR/A"}:
            continue
        accession = row["ACCESSION_NUMBER"]
        cover_row = cover.get(accession, {})
        item = _Submission(
            accession=accession,
            cik=int(row["CIK"]),
            filing_date=_parse_date(row.get("FILING_DATE")),
            report_date=_parse_date(row.get("PERIODOFREPORT")),
            submission_type=submission_type,
            manager_name=(cover_row.get("FILINGMANAGER_NAME") or f"CIK {row['CIK']}").strip(),
            amendment_type=(cover_row.get("AMENDMENTTYPE") or "").strip().upper() or None,
        )
        grouped[(item.cik, item.report_date)].append(item)

    selected: dict[str, _Submission] = {}
    for submissions in grouped.values():
        submissions.sort(key=lambda item: (item.filing_date, item.accession))
        initials = [item for item in submissions if item.submission_type == "13F-HR"]
        restatements = [
            item
            for item in submissions
            if item.amendment_type and "RESTATEMENT" in item.amendment_type
        ]
        additions = [
            item
            for item in submissions
            if item.submission_type == "13F-HR/A" and item not in restatements
        ]
        base = restatements[-1] if restatements else initials[-1] if initials else None
        if base:
            selected[base.accession] = base
        for addition in additions:
            selected[addition.accession] = addition
    return selected


def parse_13f_archive(
    path: str | Path,
    *,
    source_url: str,
    symbols: Iterable[SymbolIdentity],
    known_cusips: dict[str, str] | None = None,
    position_sink: Callable[[RawInstitutionalPosition], None] | None = None,
    retain_positions: bool = True,
    progress: Callable[[int], None] | None = None,
    progress_every_rows: int = 250_000,
) -> ArchiveResult:
    if progress_every_rows < 1:
        raise ValueError("progress_every_rows must be positive")
    if not retain_positions and position_sink is None:
        raise ValueError("position_sink is required when archive positions are not retained")
    symbol_list = tuple(symbols)
    match_index = _symbol_match_index(symbol_list)
    cusip_to_code = dict(known_cusips or {})
    matches: dict[str, CusipMatch] = {}
    # SEC archives contain millions of repeated rows. Retaining the complete issuer/class
    # strings for every unresolved CUSIP used several GiB on production. Keep only bounded
    # in-process fingerprints; they are used solely to avoid repeating the same match attempt.
    unmatched_label_fingerprints: dict[str, tuple[int, ...]] = {}

    with zipfile.ZipFile(path) as archive:
        submissions = _selected_submissions(archive)
        if not submissions:
            raise ValueError("13F archive has no selected holdings submissions")
        latest_report = max(item.report_date for item in submissions.values())
        manager_filings: dict[int, ManagerFiling] = {}
        for item in submissions.values():
            if item.report_date != latest_report:
                continue
            candidate = ManagerFiling(
                cik=item.cik,
                name=item.manager_name,
                report_date=item.report_date,
                filing_date=item.filing_date,
                accession_number=item.accession,
                source_url=filing_index_url(item.cik, item.accession),
            )
            prior_filing = manager_filings.get(item.cik)
            if prior_filing is None or (
                candidate.filing_date,
                candidate.accession_number,
            ) > (prior_filing.filing_date, prior_filing.accession_number):
                manager_filings[item.cik] = candidate
        aggregate: dict[tuple[str, int, dt.date], RawInstitutionalPosition] | None = (
            {} if retain_positions else None
        )

        def add_position(row, submission: _Submission, code: str, cusip: str) -> None:
            if submission.report_date != latest_report:
                return
            try:
                shares = int(float(row.get("SSHPRNAMT") or 0))
                value_usd = float(row.get("VALUE") or 0)
            except ValueError:
                return
            position = RawInstitutionalPosition(
                code=code,
                cusip=cusip,
                manager_cik=submission.cik,
                manager_name=submission.manager_name,
                report_date=submission.report_date,
                filing_date=submission.filing_date,
                accession_number=submission.accession,
                shares=shares,
                value_usd=value_usd,
                source_url=filing_index_url(submission.cik, submission.accession),
            )
            if position_sink is not None:
                position_sink(position)
            if aggregate is None:
                return
            key = (code, submission.cik, submission.report_date)
            prior = aggregate.get(key)
            if prior is None:
                aggregate[key] = position
            else:
                aggregate[key] = prior.model_copy(
                    update={
                        "shares": prior.shares + shares,
                        "value_usd": prior.value_usd + value_usd,
                        "filing_date": max(prior.filing_date, submission.filing_date),
                    }
                )

        late_match_rows: dict[str, int] = {}
        for row_number, row in enumerate(_rows(archive, "INFOTABLE.tsv")):
            processed_rows = row_number + 1
            if progress and processed_rows % progress_every_rows == 0:
                progress(processed_rows)
            accession = row.get("ACCESSION_NUMBER") or ""
            submission = submissions.get(accession)
            if submission is None:
                continue
            if (row.get("SSHPRNAMTTYPE") or "").strip().upper() != "SH":
                continue
            if (row.get("PUTCALL") or "").strip():
                continue
            cusip = (row.get("CUSIP") or "").strip().upper()
            if _VALID_CUSIP.fullmatch(cusip) is None:
                continue
            code = cusip_to_code.get(cusip)
            issuer_name = (row.get("NAMEOFISSUER") or "").strip()
            title_of_class = (row.get("TITLEOFCLASS") or "").strip()
            label = (issuer_name.upper(), title_of_class.upper())
            fingerprints = unmatched_label_fingerprints.get(cusip, ())
            fingerprint = hash(label)
            if (
                code is None
                and fingerprint not in fingerprints
                and len(fingerprints) < MAX_LABEL_ATTEMPTS_PER_CUSIP
            ):
                had_prior_label = bool(fingerprints)
                unmatched_label_fingerprints[cusip] = (*fingerprints, fingerprint)
                matched = _match_13f_security(issuer_name, title_of_class, match_index)
                if matched:
                    code, confidence, method = matched
                    cusip_to_code[cusip] = code
                    if had_prior_label:
                        late_match_rows[cusip] = row_number
                    unmatched_label_fingerprints.pop(cusip, None)
                    matches[cusip] = CusipMatch(
                        code=code,
                        cusip=cusip,
                        issuer_name=issuer_name,
                        title_of_class=title_of_class,
                        confidence=confidence,
                        match_method=method,
                    )
            if code is None:
                continue
            add_position(row, submission, code, cusip)

        # A CUSIP can appear under more than one official label in the same archive. If a later
        # label resolves exactly, replay only the earlier rows for that CUSIP so the first managers
        # are not silently omitted from the aggregate.
        if late_match_rows:
            last_late_row = max(late_match_rows.values())
            for row_number, row in enumerate(_rows(archive, "INFOTABLE.tsv")):
                if row_number >= last_late_row:
                    break
                cusip = (row.get("CUSIP") or "").strip().upper()
                if _VALID_CUSIP.fullmatch(cusip) is None:
                    continue
                match_row = late_match_rows.get(cusip)
                if match_row is None or row_number >= match_row:
                    continue
                submission = submissions.get(row.get("ACCESSION_NUMBER") or "")
                if submission is None:
                    continue
                if (row.get("SSHPRNAMTTYPE") or "").strip().upper() != "SH":
                    continue
                if (row.get("PUTCALL") or "").strip():
                    continue
                add_position(row, submission, cusip_to_code[cusip], cusip)
    positions = tuple(aggregate.values()) if aggregate is not None else ()
    return ArchiveResult(
        source_url=source_url,
        report_date=latest_report,
        positions=positions,
        matches=tuple(matches.values()),
        unmatched_cusips=len(unmatched_label_fingerprints),
        manager_filings=manager_filings,
    )


def _change_type(current: int, prior: int | None) -> tuple[str, int | None, float | None]:
    if prior is None or prior == 0:
        return "new", None, None
    delta = current - prior
    pct = delta / prior * 100
    if delta > 0:
        return "increased", delta, pct
    if delta < 0:
        return "reduced", delta, pct
    return "unchanged", 0, 0.0


_COMMON_SPLIT_FACTORS = (1.5, 2.0, 3.0, 4.0, 5.0, 10.0, 20.0, 25.0, 50.0, 100.0)
_MINIMUM_SHARE_BASIS_PAIRS = 5
_SPLIT_CONSENSUS_FRACTION = 0.70
_SPLIT_FACTOR_TOLERANCE = 0.12


def _share_basis_comparability(
    code: str,
    current_map: dict[tuple[str, int], RawInstitutionalPosition],
    prior_map: dict[tuple[str, int], RawInstitutionalPosition],
) -> bool | None:
    """Infer whether two 13F periods use a comparable reported-share basis.

    Yahoo closes cannot reveal splits because its raw historical close is already split-adjusted.
    Instead, this guard uses paired managers' raw SEC share counts. A CUSIP change or a broad
    cluster around a common split/reverse-split factor makes the basis unsafe. Sparse coverage
    abstains rather than claiming comparability.
    """

    pairs = [
        (current_map[(code, manager)], prior_map[(code, manager)])
        for item_code, manager in current_map
        if item_code == code and (code, manager) in prior_map
    ]
    if len(pairs) < _MINIMUM_SHARE_BASIS_PAIRS:
        return None
    if any(current.cusip != prior.cusip for current, prior in pairs):
        return False
    ratios = [
        current.shares / prior.shares
        for current, prior in pairs
        if current.shares > 0 and prior.shares > 0
    ]
    if len(ratios) < _MINIMUM_SHARE_BASIS_PAIRS:
        return None
    required_votes = max(
        _MINIMUM_SHARE_BASIS_PAIRS,
        math.ceil(len(ratios) * _SPLIT_CONSENSUS_FRACTION),
    )
    candidate_factors = (*_COMMON_SPLIT_FACTORS, *(1 / value for value in _COMMON_SPLIT_FACTORS))
    for factor in candidate_factors:
        votes = sum(abs(ratio / factor - 1.0) <= _SPLIT_FACTOR_TOLERANCE for ratio in ratios)
        if votes >= required_votes:
            return False
    return True


def build_holding_changes(
    current: ArchiveResult,
    prior: ArchiveResult,
    *,
    now: dt.datetime | None = None,
    watched_manager_ciks: frozenset[int] = frozenset(),
) -> tuple[list[InstitutionalPositionChange], list[InstitutionalSummary]]:
    now = now or dt.datetime.now(dt.UTC)
    current_map = {(row.code, row.manager_cik): row for row in current.positions}
    prior_map = {(row.code, row.manager_cik): row for row in prior.positions}
    codes = sorted({code for code, _ in current_map} | {code for code, _ in prior_map})
    stored: list[InstitutionalPositionChange] = []
    summaries: list[InstitutionalSummary] = []

    for code in codes:
        managers = sorted(
            {manager for item_code, manager in current_map if item_code == code}
            | {manager for item_code, manager in prior_map if item_code == code}
        )
        changes: list[InstitutionalPositionChange] = []
        counts = defaultdict(int)
        total_shares = 0
        total_value = 0.0
        prior_total_shares = sum(row.shares for row in prior.positions if row.code == code)
        share_basis_comparable = _share_basis_comparability(code, current_map, prior_map)
        latest_filing = current.report_date
        for manager_cik in managers:
            cur = current_map.get((code, manager_cik))
            prev = prior_map.get((code, manager_cik))
            if cur is None and prev is not None:
                current_filing = current.manager_filings.get(manager_cik)
                if current_filing is None:
                    # Absence without a comparable current filing is not evidence of an exit.
                    continue
                change_type = "exited"
                shares = 0
                value = 0.0
                delta = -prev.shares
                pct = -100.0
                reference = prev
                filing_date = current_filing.filing_date
                accession_number = current_filing.accession_number
                source_url = current_filing.source_url
            elif cur is not None:
                change_type, delta, pct = _change_type(cur.shares, prev.shares if prev else None)
                shares = cur.shares
                value = cur.value_usd
                reference = cur
                filing_date = cur.filing_date
                accession_number = cur.accession_number
                source_url = cur.source_url
                total_shares += shares
                total_value += value
            else:
                continue
            latest_filing = max(latest_filing, filing_date)
            counts[change_type] += 1
            changes.append(
                InstitutionalPositionChange(
                    code=code,
                    report_date=current.report_date,
                    manager_cik=manager_cik,
                    manager_name=reference.manager_name,
                    cusip=reference.cusip,
                    shares=shares,
                    value_usd=value,
                    prior_shares=prev.shares if prev else None,
                    share_change=delta,
                    change_pct=round(pct, 2) if pct is not None else None,
                    change_type=change_type,
                    filing_date=filing_date,
                    accession_number=accession_number,
                    source_url=source_url,
                    value_rank=0,
                )
            )

        if not changes:
            continue
        ranked = sorted(changes, key=lambda row: row.value_usd, reverse=True)
        for rank, row in enumerate(ranked, start=1):
            row.value_rank = rank
        by_change = sorted(
            changes,
            key=lambda row: abs(row.share_change or 0),
            reverse=True,
        )[:TOP_BY_CHANGE]
        prioritized = (
            [row for row in ranked if row.manager_cik in watched_manager_ciks]
            + ranked[:TOP_BY_VALUE]
            + by_change
        )
        keep: list[InstitutionalPositionChange] = []
        seen: set[tuple[int, str]] = set()
        for row in prioritized:
            key = (row.manager_cik, row.code)
            if key in seen:
                continue
            seen.add(key)
            keep.append(row)
            if len(keep) == MAX_STORED_MANAGERS_PER_SYMBOL:
                break
        stored.extend(sorted(keep, key=lambda row: row.value_rank))
        net_change = total_shares - prior_total_shares
        summaries.append(
            InstitutionalSummary(
                code=code,
                report_date=current.report_date,
                prior_report_date=prior.report_date,
                latest_filing_date=latest_filing,
                managers_count=sum(1 for row in changes if row.shares > 0),
                total_shares=total_shares,
                total_value_usd=total_value,
                new_positions=counts["new"],
                increased_positions=counts["increased"],
                reduced_positions=counts["reduced"],
                exited_positions=counts["exited"],
                unchanged_positions=counts["unchanged"],
                net_share_change=net_change,
                net_change_pct=(
                    round(net_change / prior_total_shares * 100, 2) if prior_total_shares else None
                ),
                share_basis_comparable=share_basis_comparable,
                source_url=DATASET_PAGE,
                updated_at=now,
            )
        )
    return stored, summaries
