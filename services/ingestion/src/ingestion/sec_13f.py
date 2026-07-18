"""Bounded Form 13F institutional-holdings ingestion from official SEC quarterly archives.

Two temporary ZIPs are streamed and deleted after parsing. Only confidently mapped eligible
security-master positions are considered; PostgreSQL retains all-manager summaries and at most 150
manager rows per symbol/report period, prioritizing explicitly watched managers.

    uv run python -m ingestion.sec_13f
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import and_, case, delete, distinct, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.config import get_settings
from bulls.core.db import get_sessionmaker
from bulls.core.institutional_watch import WATCHED_MANAGER_CIKS
from bulls.core.models import (
    InstitutionalHoldingSummary,
    InstitutionalManager,
    InstitutionalPosition,
    RegulatoryDataState,
    SecurityIdentifier,
    SecurityMaster,
    Symbol,
)
from bulls.market_data.providers.sec_13f import (
    DATASET_PAGE,
    ArchiveResult,
    CusipMatch,
    ManagerFiling,
    RawInstitutionalPosition,
    SymbolIdentity,
    build_holding_changes,
    discover_dataset_urls,
    parse_13f_archive,
)
from ingestion.alerts import fan_out_evidence_alert, institutional_alert_text

MARKET = "US"
SOURCE = "sec_13f"
TENANT_ID = "bullsofwallst"
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
RETENTION_QUARTERS = 8
UPSERT_BATCH_ROWS = 1000
HTTP_RETRIES = 8
RETRY_BASE_SECONDS = 5.0
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAPPING_SCOPE = "eligible_plus_restricted_research_v3"
ARCHIVE_CACHE_SCHEMA_VERSION = 1
DEFAULT_ARCHIVE_CACHE_DIR = Path("var/sec-13f-cache")
_ARCHIVE_NAME = re.compile(
    r"^(?P<prefix>.*/)(?P<start_day>\d{2})(?P<start_month>[a-z]{3})(?P<start_year>\d{4})-"
    r"(?P<end_day>\d{2})(?P<end_month>[a-z]{3})(?P<end_year>\d{4})_form13f\.zip$"
)
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def _headers() -> dict[str, str]:
    contact = get_settings().sec_contact_email
    return {
        "User-Agent": f"BullsOfTheWorld/1.0 {contact}",
        "Accept-Encoding": "gzip, deflate",
    }


async def _download(client: httpx.AsyncClient, url: str, target: Path) -> int:
    total = 0
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        content_length = int(response.headers.get("content-length") or 0)
        if content_length > MAX_ARCHIVE_BYTES:
            raise ValueError(f"13F archive exceeds {MAX_ARCHIVE_BYTES} bytes")
        with target.open("wb") as output:
            async for chunk in response.aiter_bytes(1024 * 1024):
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise ValueError(
                        f"13F archive exceeded {MAX_ARCHIVE_BYTES} bytes while streaming"
                    )
                output.write(chunk)
    return total


async def _dataset_urls(*, retries: int = HTTP_RETRIES) -> list[str]:
    async with httpx.AsyncClient(headers=_headers(), timeout=60, follow_redirects=True) as client:
        for attempt in range(retries):
            try:
                page = await client.get(DATASET_PAGE)
                page.raise_for_status()
                break
            except httpx.HTTPError as error:
                if attempt == retries - 1 or not _retryable_http_error(error):
                    raise
                delay = _retry_delay(error, attempt)
                print(
                    f"  ! SEC dataset index retry {attempt + 1}/{retries} "
                    f"in {delay:.0f}s ({type(error).__name__})",
                    flush=True,
                )
                await asyncio.sleep(delay)
    return discover_dataset_urls(page.text)


def _retryable_http_error(error: httpx.HTTPError) -> bool:
    return isinstance(error, httpx.TransportError) or (
        isinstance(error, httpx.HTTPStatusError) and error.response.status_code in RETRYABLE_STATUS
    )


def _retry_delay(error: httpx.HTTPError, attempt: int) -> float:
    if isinstance(error, httpx.HTTPStatusError):
        retry_after = error.response.headers.get("retry-after", "")
        try:
            return min(60.0, max(1.0, float(retry_after)))
        except ValueError:
            pass
    return min(60.0, RETRY_BASE_SECONDS * (2**attempt))


def _archive_sequence(checkpoint_url: str, count: int) -> list[str]:
    """Derive prior official archive windows from a trusted SEC checkpoint URL."""
    parsed = urlparse(checkpoint_url)
    if parsed.scheme != "https" or parsed.hostname not in {"sec.gov", "www.sec.gov"}:
        return []
    match = _ARCHIVE_NAME.match(parsed.path)
    if match is None or "/form-13f-data-sets/" not in parsed.path:
        return []
    try:
        start = dt.date(
            int(match.group("start_year")),
            _MONTHS.index(match.group("start_month")) + 1,
            int(match.group("start_day")),
        )
        provided_end = dt.date(
            int(match.group("end_year")),
            _MONTHS.index(match.group("end_month")) + 1,
            int(match.group("end_day")),
        )
    except (ValueError, IndexError):
        return []
    initial_next_index = start.year * 12 + start.month - 1 + 3
    expected_end = dt.date(
        initial_next_index // 12,
        initial_next_index % 12 + 1,
        1,
    ) - dt.timedelta(days=1)
    if start.day != 1 or provided_end != expected_end:
        return []
    prefix = f"https://www.sec.gov{match.group('prefix')}"
    urls = []
    for _ in range(count):
        next_start_index = start.year * 12 + start.month - 1 + 3
        prior_start_index = start.year * 12 + start.month - 4
        next_start = dt.date(
            next_start_index // 12,
            next_start_index % 12 + 1,
            1,
        )
        prior_start = dt.date(
            prior_start_index // 12,
            prior_start_index % 12 + 1,
            1,
        )
        end = next_start - dt.timedelta(days=1)
        urls.append(
            f"{prefix}{start:%d}{_MONTHS[start.month - 1]}{start:%Y}-"
            f"{end:%d}{_MONTHS[end.month - 1]}{end:%Y}_form13f.zip"
        )
        start = prior_start
    return urls


def _is_consecutive_report_pair(current: dt.date, prior: dt.date) -> bool:
    current_quarter_start_month = ((current.month - 1) // 3) * 3 + 1
    current_quarter_start = dt.date(
        current.year,
        current_quarter_start_month,
        1,
    )
    next_quarter_index = current.year * 12 + current_quarter_start_month - 1 + 3
    current_quarter_end = dt.date(
        next_quarter_index // 12,
        next_quarter_index % 12 + 1,
        1,
    ) - dt.timedelta(days=1)
    return current == current_quarter_end and prior == current_quarter_start - dt.timedelta(days=1)


async def _checkpoint_archive_urls(count: int) -> list[str]:
    sm = get_sessionmaker()
    async with sm() as session:
        state = await session.get(RegulatoryDataState, (MARKET, SOURCE))
    checkpoint = (state.details or {}).get("current_archive_url") if state else None
    return _archive_sequence(str(checkpoint or ""), count)


async def _download_archive(
    client: httpx.AsyncClient, directory: Path, url: str, index: int
) -> tuple[Path, int]:
    target = directory / f"dataset-{index}.zip"
    for attempt in range(HTTP_RETRIES):
        try:
            return target, await _download(client, url, target)
        except httpx.HTTPError as error:
            target.unlink(missing_ok=True)
            if attempt == HTTP_RETRIES - 1 or not _retryable_http_error(error):
                raise
            delay = _retry_delay(error, attempt)
            print(
                f"  ! archive retry {attempt + 1}/{HTTP_RETRIES} in {delay:.0f}s "
                f"({type(error).__name__})",
                flush=True,
            )
            await asyncio.sleep(delay)
    raise RuntimeError("unreachable")


def _normalize_codes(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    return sorted({code.strip().upper() for code in raw.split(",") if code.strip()})


def _selected_archive_urls(urls: list[str], history_quarters: int) -> list[str]:
    selected = list(reversed(urls[: history_quarters + 1]))
    if len(selected) < history_quarters + 1:
        raise RuntimeError(
            f"SEC page listed {len(selected)} archives; {history_quarters + 1} required"
        )
    return selected


def _archive_cache_dir() -> Path:
    return Path(os.environ.get("BULLS_SEC_13F_CACHE_DIR", DEFAULT_ARCHIVE_CACHE_DIR))


def _mapping_fingerprint(symbols: list[SymbolIdentity]) -> str:
    digest = hashlib.sha256()
    digest.update(f"{MAPPING_SCOPE}\n".encode())
    for symbol in sorted(symbols, key=lambda row: (row.code, row.name)):
        digest.update(f"{symbol.code}\0{symbol.name}\n".encode())
    return digest.hexdigest()


def _archive_cache_path(cache_dir: Path, source_url: str, fingerprint: str) -> Path:
    url_digest = hashlib.sha256(source_url.encode()).hexdigest()[:20]
    return cache_dir / (
        f"sec13f-v{ARCHIVE_CACHE_SCHEMA_VERSION}-{fingerprint[:20]}-{url_digest}.json.gz"
    )


def _store_archive_cache(
    cache_dir: Path,
    archive: ArchiveResult,
    *,
    fingerprint: str,
) -> Path:
    target = _archive_cache_path(cache_dir, archive.source_url, fingerprint)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": ARCHIVE_CACHE_SCHEMA_VERSION,
        "mapping_scope": MAPPING_SCOPE,
        "mapping_fingerprint": fingerprint,
        "source_url": archive.source_url,
        "report_date": archive.report_date.isoformat(),
        "positions": [row.model_dump(mode="json") for row in archive.positions],
        "matches": [row.model_dump(mode="json") for row in archive.matches],
        "unmatched_cusips": archive.unmatched_cusips,
        "manager_filings": [
            {
                "cik": row.cik,
                "name": row.name,
                "report_date": row.report_date.isoformat(),
                "filing_date": row.filing_date.isoformat(),
                "accession_number": row.accession_number,
                "source_url": row.source_url,
            }
            for row in archive.manager_filings.values()
        ],
    }
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    with gzip.open(temporary, "wt", encoding="utf-8") as output:
        json.dump(payload, output, separators=(",", ":"), sort_keys=True)
    temporary.chmod(0o600)
    temporary.replace(target)
    return target


def _load_archive_cache(
    cache_dir: Path,
    source_url: str,
    *,
    fingerprint: str,
) -> ArchiveResult | None:
    target = _archive_cache_path(cache_dir, source_url, fingerprint)
    if not target.exists():
        return None
    try:
        with gzip.open(target, "rt", encoding="utf-8") as source:
            payload = json.load(source)
        if (
            payload["schema_version"] != ARCHIVE_CACHE_SCHEMA_VERSION
            or payload["mapping_scope"] != MAPPING_SCOPE
            or payload["mapping_fingerprint"] != fingerprint
            or payload["source_url"] != source_url
        ):
            raise ValueError("13F derived cache provenance mismatch")
        manager_filings = {
            int(row["cik"]): ManagerFiling(
                cik=int(row["cik"]),
                name=str(row["name"]),
                report_date=dt.date.fromisoformat(row["report_date"]),
                filing_date=dt.date.fromisoformat(row["filing_date"]),
                accession_number=str(row["accession_number"]),
                source_url=str(row["source_url"]),
            )
            for row in payload["manager_filings"]
        }
        return ArchiveResult(
            source_url=source_url,
            report_date=dt.date.fromisoformat(payload["report_date"]),
            positions=tuple(
                RawInstitutionalPosition.model_validate(row) for row in payload["positions"]
            ),
            matches=tuple(CusipMatch.model_validate(row) for row in payload["matches"]),
            unmatched_cusips=int(payload["unmatched_cusips"]),
            manager_filings=manager_filings,
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        # A partial/corrupt derived cache must never become research evidence. Remove it so
        # the official archive is downloaded and parsed again on this run.
        target.unlink(missing_ok=True)
        return None


def _prune_archive_cache(
    cache_dir: Path,
    *,
    fingerprint: str,
    keep_urls: list[str],
) -> None:
    keep = {_archive_cache_path(cache_dir, url, fingerprint) for url in keep_urls}
    for path in cache_dir.glob(
        f"sec13f-v{ARCHIVE_CACHE_SCHEMA_VERSION}-{fingerprint[:20]}-*.json.gz"
    ):
        if path not in keep:
            path.unlink(missing_ok=True)


async def _symbol_context(
    codes: list[str] | None = None,
) -> tuple[list[SymbolIdentity], dict[str, str]]:
    sm = get_sessionmaker()
    async with sm() as session:
        names_stmt = (
            select(SecurityMaster.symbol, SecurityMaster.security_name)
            .outerjoin(
                Symbol,
                (Symbol.market == SecurityMaster.market) & (Symbol.code == SecurityMaster.symbol),
            )
            .where(
                SecurityMaster.market == MARKET,
                SecurityMaster.is_active.is_(True),
                SecurityMaster.instrument_type.in_(("common_stock", "adr", "etf")),
                or_(
                    SecurityMaster.is_product_eligible.is_(True),
                    and_(
                        Symbol.is_active.is_(True),
                        Symbol.is_hidden.is_(True),
                        Symbol.data_status.in_(("onboarding", "degraded")),
                        SecurityMaster.exclude_reason.like("financial_status_%"),
                    ),
                ),
            )
        )
        identifier_stmt = select(SecurityIdentifier.identifier, SecurityIdentifier.code).where(
            SecurityIdentifier.market == MARKET,
            SecurityIdentifier.identifier_type == "cusip",
        )
        if codes is not None:
            names_stmt = names_stmt.where(SecurityMaster.symbol.in_(codes))
            identifier_stmt = identifier_stmt.where(SecurityIdentifier.code.in_(codes))
        names = (await session.execute(names_stmt.order_by(SecurityMaster.symbol))).all()
        identifiers = (await session.execute(identifier_stmt)).all()
    return (
        [SymbolIdentity(code=code, name=name) for code, name in names],
        {identifier: code for identifier, code in identifiers},
    )


async def _upsert(session, model, rows: list[dict], keys: tuple[str, ...]) -> int:
    if not rows:
        return 0
    for start in range(0, len(rows), UPSERT_BATCH_ROWS):
        batch = rows[start : start + UPSERT_BATCH_ROWS]
        stmt = pg_insert(model).values(batch)
        updates = {column: stmt.excluded[column] for column in batch[0] if column not in keys}
        await session.execute(stmt.on_conflict_do_update(index_elements=list(keys), set_=updates))
    return len(rows)


async def _upsert_managers(session, rows: list[dict]) -> int:
    if not rows:
        return 0
    for start in range(0, len(rows), UPSERT_BATCH_ROWS):
        batch = rows[start : start + UPSERT_BATCH_ROWS]
        stmt = pg_insert(InstitutionalManager).values(batch)
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["cik"],
                set_={
                    "name": case(
                        (
                            InstitutionalManager.latest_report_date.is_(None),
                            stmt.excluded.name,
                        ),
                        (
                            stmt.excluded.latest_report_date
                            >= InstitutionalManager.latest_report_date,
                            stmt.excluded.name,
                        ),
                        else_=InstitutionalManager.name,
                    ),
                    "latest_report_date": func.greatest(
                        InstitutionalManager.latest_report_date,
                        stmt.excluded.latest_report_date,
                    ),
                    "latest_filing_date": func.greatest(
                        InstitutionalManager.latest_filing_date,
                        stmt.excluded.latest_filing_date,
                    ),
                    "updated_at": stmt.excluded.updated_at,
                },
            )
        )
    return len(rows)


async def _persist_period(
    current, changes, summaries, *, codes: list[str] | None = None
) -> dict[str, int]:
    now = dt.datetime.now(dt.UTC)
    manager_rows: dict[int, dict] = {}
    for row in changes:
        manager_rows[row.manager_cik] = {
            "cik": row.manager_cik,
            "name": row.manager_name,
            "latest_report_date": row.report_date,
            "latest_filing_date": row.filing_date,
            "updated_at": now,
        }
    identifier_rows_by_cusip = {
        match.cusip: {
            "market": MARKET,
            "code": match.code,
            "identifier_type": "cusip",
            "identifier": match.cusip,
            "source": "sec_13f",
            "match_method": match.match_method,
            "confidence": match.confidence,
            "verified_at": now,
        }
        for match in current.matches
    }
    identifier_rows = list(identifier_rows_by_cusip.values())
    position_rows = [row.model_dump() for row in changes]
    summary_rows = [row.model_dump() for row in summaries]
    cutoff = current.report_date - dt.timedelta(days=(RETENTION_QUARTERS - 1) * 93 + 15)

    sm = get_sessionmaker()
    async with sm() as session:
        position_delete, summary_delete = _period_deletes(current.report_date, codes)
        await session.execute(position_delete)
        await session.execute(summary_delete)
        await _upsert(
            session,
            SecurityIdentifier,
            identifier_rows,
            ("market", "identifier_type", "identifier"),
        )
        await _upsert_managers(session, list(manager_rows.values()))
        await _upsert(
            session,
            InstitutionalPosition,
            position_rows,
            ("market", "code", "report_date", "manager_cik"),
        )
        await _upsert(
            session,
            InstitutionalHoldingSummary,
            summary_rows,
            ("market", "code", "report_date"),
        )
        position_prune = delete(InstitutionalPosition).where(
            InstitutionalPosition.market == MARKET,
            InstitutionalPosition.report_date < cutoff,
        )
        summary_prune = delete(InstitutionalHoldingSummary).where(
            InstitutionalHoldingSummary.market == MARKET,
            InstitutionalHoldingSummary.report_date < cutoff,
        )
        if codes is not None:
            position_prune = position_prune.where(InstitutionalPosition.code.in_(codes))
            summary_prune = summary_prune.where(InstitutionalHoldingSummary.code.in_(codes))
        await session.execute(position_prune)
        await session.execute(summary_prune)
        await session.commit()
    return {
        "positions": len(changes),
        "summaries": len(summaries),
        "identifiers": len(identifier_rows),
        "managers": len(manager_rows),
    }


def _period_deletes(report_date: dt.date, codes: list[str] | None = None):
    position_delete = delete(InstitutionalPosition).where(
        InstitutionalPosition.market == MARKET,
        InstitutionalPosition.report_date == report_date,
    )
    summary_delete = delete(InstitutionalHoldingSummary).where(
        InstitutionalHoldingSummary.market == MARKET,
        InstitutionalHoldingSummary.report_date == report_date,
    )
    if codes is not None:
        position_delete = position_delete.where(InstitutionalPosition.code.in_(codes))
        summary_delete = summary_delete.where(InstitutionalHoldingSummary.code.in_(codes))
    return position_delete, summary_delete


async def _persist_state(
    *,
    newest,
    baseline,
    downloaded_bytes: int,
    requested_quarters: int,
    new_matches: int,
    unmatched_cusips: int,
    archive_cache_hits: int,
) -> dict[str, int]:
    now = dt.datetime.now(dt.UTC)
    sm = get_sessionmaker()
    async with sm() as session:
        positions = await session.scalar(
            select(func.count())
            .select_from(InstitutionalPosition)
            .where(InstitutionalPosition.market == MARKET)
        )
        summaries = await session.scalar(
            select(func.count())
            .select_from(InstitutionalHoldingSummary)
            .where(InstitutionalHoldingSummary.market == MARKET)
        )
        periods = await session.scalar(
            select(func.count(distinct(InstitutionalHoldingSummary.report_date))).where(
                InstitutionalHoldingSummary.market == MARKET
            )
        )
        symbols = await session.scalar(
            select(func.count(distinct(InstitutionalHoldingSummary.code))).where(
                InstitutionalHoldingSummary.market == MARKET,
                InstitutionalHoldingSummary.report_date == newest.report_date,
            )
        )
        state = {
            "market": MARKET,
            "source": SOURCE,
            "as_of_date": newest.report_date,
            "last_success_at": now,
            "records": int(positions or 0) + int(summaries or 0),
            "symbols_covered": int(symbols or 0),
            "downloaded_bytes": downloaded_bytes,
            "details": {
                "baseline_report_date": baseline.report_date.isoformat(),
                "positions_retained": int(positions or 0),
                "all_manager_summaries": int(summaries or 0),
                "history_quarters_loaded": int(periods or 0),
                "requested_quarters": requested_quarters,
                "new_cusip_matches": new_matches,
                "unmatched_cusips": unmatched_cusips,
                "derived_archive_cache_hits": archive_cache_hits,
                "retention": f"{RETENTION_QUARTERS} quarters; max 150 managers/symbol/quarter",
                "mapping_scope": MAPPING_SCOPE,
                "watched_manager_ciks": sorted(WATCHED_MANAGER_CIKS),
                "raw_archives_retained": False,
                "derived_archive_cache_schema": ARCHIVE_CACHE_SCHEMA_VERSION,
                "current_archive_url": newest.source_url,
            },
        }
        await _upsert(session, RegulatoryDataState, [state], ("market", "source"))
        await session.commit()
    return {
        "positions": int(positions or 0),
        "summaries": int(summaries or 0),
        "history_quarters": int(periods or 0),
    }


def _is_refresh_current(details: dict | None, candidate_url: str, requested_quarters: int) -> bool:
    details = details or {}
    return bool(
        details.get("current_archive_url") == candidate_url
        and int(details.get("history_quarters_loaded") or 1) >= requested_quarters
        and details.get("mapping_scope") == MAPPING_SCOPE
    )


async def _already_current(candidate_url: str, requested_quarters: int) -> bool:
    sm = get_sessionmaker()
    async with sm() as session:
        state = await session.get(RegulatoryDataState, (MARKET, SOURCE))
        current = bool(
            state and _is_refresh_current(state.details, candidate_url, requested_quarters)
        )
        if current and state is not None:
            checked_at = dt.datetime.now(dt.UTC)
            state.last_success_at = checked_at
            state.details = {
                **(state.details or {}),
                "last_checked_at": checked_at.isoformat(),
            }
            await session.commit()
    return current


async def collect(
    *,
    force: bool = False,
    history_quarters: int = 1,
    codes: list[str] | None = None,
) -> dict[str, int]:
    if not 1 <= history_quarters <= RETENTION_QUARTERS:
        raise ValueError(f"history_quarters must be between 1 and {RETENTION_QUARTERS}")
    symbols, known_cusips = await _symbol_context(codes)
    if codes is not None and len(symbols) != len(codes):
        found = {symbol.code for symbol in symbols}
        missing = sorted(set(codes) - found)
        raise ValueError(f"unsupported or unknown target symbols: {', '.join(missing)}")
    try:
        urls = await _dataset_urls(retries=1 if force else HTTP_RETRIES)
    except httpx.HTTPError:
        if not force:
            raise
        urls = await _checkpoint_archive_urls(history_quarters + 1)
        if urls:
            print(
                "  ! SEC index unavailable; using validated official checkpoint windows "
                "for forced recovery",
                flush=True,
            )
    if not urls:
        raise RuntimeError("SEC page did not list Form 13F archives")
    if codes is None and not force and await _already_current(urls[0], history_quarters):
        return {
            "symbols_requested": len(symbols),
            "history_quarters": history_quarters,
            "skipped_current": 1,
        }

    # The SEC index is newest-first. Parsing oldest-first lets exact CUSIP matches learned from
    # a baseline quarter improve every later quarter in the same run.
    selected_urls = _selected_archive_urls(urls, history_quarters)
    cache_dir = _archive_cache_dir()
    mapping_fingerprint = _mapping_fingerprint(symbols)

    summaries_to_index = []
    period_stats: list[dict[str, int]] = []
    downloaded_bytes = 0
    new_matches = 0
    unmatched_cusips = 0
    completed = 0
    archive_cache_hits = 0
    newest = None
    baseline = None
    prior = None

    with tempfile.TemporaryDirectory(prefix="bulls-sec-13f-") as temp:
        async with httpx.AsyncClient(
            headers=_headers(), timeout=180, follow_redirects=True
        ) as client:
            for index, url in enumerate(selected_urls):
                archive = _load_archive_cache(
                    cache_dir,
                    url,
                    fingerprint=mapping_fingerprint,
                )
                size = 0
                if archive is not None:
                    archive_cache_hits += 1
                    print(
                        f"  ...loaded derived archive checkpoint {index + 1}/"
                        f"{len(selected_urls)} ({archive.report_date})",
                        flush=True,
                    )
                else:
                    path = None
                    try:
                        print(
                            f"  ...downloading archive {index + 1}/{len(selected_urls)}",
                            flush=True,
                        )
                        path, size = await _download_archive(client, Path(temp), url, index)
                        print(
                            f"  ...parsing archive {index + 1}/{len(selected_urls)} "
                            f"({size / 1024 / 1024:.1f} MiB)",
                            flush=True,
                        )
                        archive = parse_13f_archive(
                            path,
                            source_url=url,
                            symbols=symbols,
                            known_cusips=known_cusips,
                            progress=lambda rows, archive_number=index + 1: print(
                                f"  ...archive {archive_number}: scanned {rows:,} holdings rows",
                                flush=True,
                            ),
                        )
                        _store_archive_cache(
                            cache_dir,
                            archive,
                            fingerprint=mapping_fingerprint,
                        )
                    except (httpx.HTTPError, ValueError) as error:
                        print(f"  ! skipped 13F archive {url} ({error})", flush=True)
                        continue
                    finally:
                        if path is not None:
                            path.unlink(missing_ok=True)

                downloaded_bytes += size
                new_matches += len(archive.matches)
                unmatched_cusips += archive.unmatched_cusips
                known_cusips.update({row.cusip: row.code for row in archive.matches})
                if prior is None:
                    prior = archive
                    baseline = archive
                    continue
                current = archive
                if not _is_consecutive_report_pair(current.report_date, prior.report_date):
                    raise RuntimeError(
                        "13F data sets are not consecutive quarter ends: "
                        f"{prior.report_date} then {current.report_date}"
                    )
                changes, summaries = build_holding_changes(
                    current,
                    prior,
                    watched_manager_ciks=WATCHED_MANAGER_CIKS,
                )
                period_stats.append(await _persist_period(current, changes, summaries, codes=codes))
                summaries_to_index.extend(summaries)
                completed += 1
                newest = current
                print(
                    f"  ...stored {completed}/{history_quarters} quarters "
                    f"({current.report_date}, {len(summaries)} symbols)",
                    flush=True,
                )
                if completed == history_quarters:
                    break
                prior = current

        if completed < history_quarters or newest is None or baseline is None:
            raise RuntimeError(
                f"SEC page provided {completed} comparable quarters; {history_quarters} requested"
            )

        if codes is None:
            stats = await _persist_state(
                newest=newest,
                baseline=baseline,
                downloaded_bytes=downloaded_bytes,
                requested_quarters=history_quarters,
                new_matches=new_matches,
                unmatched_cusips=unmatched_cusips,
                archive_cache_hits=archive_cache_hits,
            )
            _prune_archive_cache(
                cache_dir,
                fingerprint=mapping_fingerprint,
                keep_urls=selected_urls,
            )
        else:
            stats = {
                "positions": sum(row["positions"] for row in period_stats),
                "summaries": sum(row["summaries"] for row in period_stats),
                "history_quarters": completed,
            }
        alerts_delivered = 0
        sm = get_sessionmaker()
        async with sm() as session:
            for summary in summaries_to_index:
                if summary.report_date != newest.report_date:
                    continue
                title, body = institutional_alert_text(
                    summary.code,
                    summary.report_date,
                    summary.net_change_pct,
                    summary.managers_count,
                )
                alerts_delivered += await fan_out_evidence_alert(
                    session,
                    tenant_id=TENANT_ID,
                    market=MARKET,
                    code=summary.code,
                    source_key=f"sec13f:{summary.code}:{summary.report_date}",
                    kind="ownership",
                    title_i18n=title,
                    body_i18n=body,
                )
            await session.commit()
        settings = get_settings()
        redis = await create_pool(
            RedisSettings.from_dsn(settings.redis_url),
            default_queue_name=settings.ai_queue_name,
        )
        try:
            for summary in summaries_to_index:
                await redis.enqueue_job(
                    "embed_institutional_summary",
                    MARKET,
                    summary.code,
                    summary.report_date.isoformat(),
                    _job_id=(f"embed:sec-13f:v3:{MARKET}:{summary.code}:{summary.report_date}"),
                )
        finally:
            await redis.aclose()
    return {
        **stats,
        "period_positions_written": sum(row["positions"] for row in period_stats),
        "period_summaries_written": sum(row["summaries"] for row in period_stats),
        "symbols_requested": len(symbols),
        "current_report": int(newest.report_date.strftime("%Y%m%d")),
        "baseline_report": int(baseline.report_date.strftime("%Y%m%d")),
        "downloaded_bytes": downloaded_bytes,
        "derived_archive_cache_hits": archive_cache_hits,
        "alerts_delivered": alerts_delivered,
    }


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest bounded SEC Form 13F history")
    parser.add_argument(
        "--history-quarters",
        type=int,
        default=1,
        choices=range(1, RETENTION_QUARTERS + 1),
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--codes", help="comma-separated eligible symbols to process safely")
    return parser.parse_args(argv)


def main() -> None:
    args = _args()
    codes = _normalize_codes(args.codes)
    print(
        f"[sec-13f] refreshing {args.history_quarters} bounded institutional quarters",
        flush=True,
    )
    stats = asyncio.run(
        collect(force=args.force, history_quarters=args.history_quarters, codes=codes)
    )
    print(f"[sec-13f] done: {stats}", flush=True)


if __name__ == "__main__":
    main()
