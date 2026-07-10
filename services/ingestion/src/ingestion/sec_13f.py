"""Bounded Form 13F institutional-holdings ingestion from official SEC quarterly archives.

Two temporary ZIPs are streamed and deleted after parsing. Only confidently mapped launch-universe
positions are considered; PostgreSQL retains all-manager summaries and at most 150 manager rows per
symbol/report period.

    uv run python -m ingestion.sec_13f
"""

from __future__ import annotations

import asyncio
import datetime as dt
import tempfile
from pathlib import Path

import httpx
from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.config import get_settings
from bulls.core.db import get_sessionmaker
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
    SymbolIdentity,
    build_holding_changes,
    discover_dataset_urls,
    parse_13f_archive,
)

MARKET = "US"
SOURCE = "sec_13f"
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
RETENTION_QUARTERS = 8


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


async def _dataset_urls() -> list[str]:
    async with httpx.AsyncClient(headers=_headers(), timeout=60, follow_redirects=True) as client:
        page = await client.get(DATASET_PAGE)
        page.raise_for_status()
    return discover_dataset_urls(page.text)


async def _download_latest_two(directory: Path, urls: list[str]) -> list[tuple[str, Path, int]]:
    async with httpx.AsyncClient(headers=_headers(), timeout=180, follow_redirects=True) as client:
        downloads: list[tuple[str, Path, int]] = []
        for index, url in enumerate(urls):
            target = directory / f"dataset-{index}.zip"
            try:
                size = await _download(client, url, target)
            except (httpx.HTTPError, ValueError) as error:
                print(f"  ! skipped 13F archive {url} ({error})")
                continue
            downloads.append((url, target, size))
            if len(downloads) == 2:
                break
        if len(downloads) < 2:
            raise RuntimeError("SEC page did not provide two downloadable Form 13F archives")
        return downloads


async def _symbol_context() -> tuple[list[SymbolIdentity], dict[str, str]]:
    sm = get_sessionmaker()
    async with sm() as session:
        names = (
            await session.execute(
                select(Symbol.code, SecurityMaster.security_name)
                .join(
                    SecurityMaster,
                    (SecurityMaster.market == Symbol.market)
                    & (SecurityMaster.symbol == Symbol.code),
                )
                .where(
                    Symbol.market == MARKET,
                    Symbol.is_active.is_(True),
                    Symbol.is_hidden.is_(False),
                    Symbol.data_status == "ready",
                )
            )
        ).all()
        identifiers = (
            await session.execute(
                select(SecurityIdentifier.identifier, SecurityIdentifier.code).where(
                    SecurityIdentifier.market == MARKET,
                    SecurityIdentifier.identifier_type == "cusip",
                )
            )
        ).all()
    return (
        [SymbolIdentity(code=code, name=name) for code, name in names],
        {identifier: code for identifier, code in identifiers},
    )


async def _upsert(session, model, rows: list[dict], keys: tuple[str, ...]) -> int:
    if not rows:
        return 0
    stmt = pg_insert(model).values(rows)
    updates = {column: getattr(stmt.excluded, column) for column in rows[0] if column not in keys}
    await session.execute(stmt.on_conflict_do_update(index_elements=list(keys), set_=updates))
    return len(rows)


async def _persist(current, prior, downloaded_bytes: int, changes, summaries) -> dict[str, int]:
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
        await session.execute(
            delete(InstitutionalPosition).where(
                InstitutionalPosition.market == MARKET,
                InstitutionalPosition.report_date == current.report_date,
            )
        )
        await session.execute(
            delete(InstitutionalHoldingSummary).where(
                InstitutionalHoldingSummary.market == MARKET,
                InstitutionalHoldingSummary.report_date == current.report_date,
            )
        )
        await _upsert(
            session,
            SecurityIdentifier,
            identifier_rows,
            ("market", "identifier_type", "identifier"),
        )
        await _upsert(session, InstitutionalManager, list(manager_rows.values()), ("cik",))
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
        await session.execute(
            delete(InstitutionalPosition).where(
                InstitutionalPosition.market == MARKET,
                InstitutionalPosition.report_date < cutoff,
            )
        )
        await session.execute(
            delete(InstitutionalHoldingSummary).where(
                InstitutionalHoldingSummary.market == MARKET,
                InstitutionalHoldingSummary.report_date < cutoff,
            )
        )
        state = {
            "market": MARKET,
            "source": SOURCE,
            "as_of_date": current.report_date,
            "last_success_at": now,
            "records": len(changes) + len(summaries),
            "symbols_covered": len(summaries),
            "downloaded_bytes": downloaded_bytes,
            "details": {
                "prior_report_date": prior.report_date.isoformat(),
                "positions_retained": len(changes),
                "all_manager_summaries": len(summaries),
                "new_cusip_matches": len(current.matches),
                "unmatched_cusips": current.unmatched_cusips,
                "retention": f"{RETENTION_QUARTERS} quarters; max 150 managers/symbol/quarter",
                "raw_archives_retained": False,
                "current_archive_url": current.source_url,
            },
        }
        await _upsert(session, RegulatoryDataState, [state], ("market", "source"))
        await session.commit()
    return {
        "positions": len(changes),
        "summaries": len(summaries),
        "identifiers": len(identifier_rows),
        "managers": len(manager_rows),
    }


async def _already_current(candidate_url: str) -> bool:
    sm = get_sessionmaker()
    async with sm() as session:
        state = await session.get(RegulatoryDataState, (MARKET, SOURCE))
    return bool(state and (state.details or {}).get("current_archive_url") == candidate_url)


async def collect(*, force: bool = False) -> dict[str, int]:
    symbols, known_cusips = await _symbol_context()
    urls = await _dataset_urls()
    if not urls:
        raise RuntimeError("SEC page did not list Form 13F archives")
    if not force and await _already_current(urls[0]):
        return {"symbols_requested": len(symbols), "skipped_current": 1}
    with tempfile.TemporaryDirectory(prefix="bulls-sec-13f-") as temp:
        downloads = await _download_latest_two(Path(temp), urls)
        current_url, current_path, current_bytes = downloads[0]
        prior_url, prior_path, prior_bytes = downloads[1]
        current = parse_13f_archive(
            current_path,
            source_url=current_url,
            symbols=symbols,
            known_cusips=known_cusips,
        )
        expanded_cusips = {**known_cusips, **{row.cusip: row.code for row in current.matches}}
        prior = parse_13f_archive(
            prior_path,
            source_url=prior_url,
            symbols=symbols,
            known_cusips=expanded_cusips,
        )
        if current.report_date <= prior.report_date:
            raise RuntimeError(
                f"13F data sets are not descending: {current.report_date} <= {prior.report_date}"
            )
        changes, summaries = build_holding_changes(current, prior)
        stats = await _persist(current, prior, current_bytes + prior_bytes, changes, summaries)
        settings = get_settings()
        redis = await create_pool(
            RedisSettings.from_dsn(settings.redis_url),
            default_queue_name=settings.ai_queue_name,
        )
        try:
            for summary in summaries:
                await redis.enqueue_job(
                    "embed_institutional_summary",
                    MARKET,
                    summary.code,
                    summary.report_date.isoformat(),
                    _job_id=(f"embed:sec-13f:{MARKET}:{summary.code}:{summary.report_date}"),
                )
        finally:
            await redis.aclose()
    return {
        **stats,
        "symbols_requested": len(symbols),
        "current_report": int(current.report_date.strftime("%Y%m%d")),
        "prior_report": int(prior.report_date.strftime("%Y%m%d")),
        "downloaded_bytes": current_bytes + prior_bytes,
    }


def main() -> None:
    print("[sec-13f] refreshing bounded institutional holdings")
    stats = asyncio.run(collect())
    print(f"[sec-13f] done: {stats}")


if __name__ == "__main__":
    main()
