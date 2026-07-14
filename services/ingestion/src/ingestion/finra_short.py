"""FINRA Reg SHO daily short-sale volume ingestion (US, whole ticker universe).

FINRA publishes a consolidated NMS file each evening (~18:00 ET) at
`cdn.finra.org/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt`, pipe-delimited
(`Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market`) with a bare record-count trailer
line. Volumes can be fractional (odd lots), so source precision is retained. A day FINRA hasn't
published (weekend, holiday, or too early) returns 403/404; that is a routine skip, never an
error. Each run also catches up on any recent sessions still missing, so a missed evening heals
itself the next day without a separate recovery job.

    uv run python -m ingestion.finra_short           # today + catch-up
    uv run python -m ingestion.finra_short 2026-07-10  # one explicit session date
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import sys
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.db import get_sessionmaker
from bulls.core.models import RegulatoryDataState, SecurityMaster, ShortVolumeDaily, Symbol
from bulls.market_data.calendar import is_trading_day, to_market_tz

log = logging.getLogger(__name__)

MARKET = "US"
_URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{ymd}.txt"
_UA = "Mozilla/5.0 BullsOfTheWorld/0.1 finra-regsho"
_CATCHUP_SESSIONS = 25  # initial month of history makes the baseline useful immediately
_RETENTION_DAYS = 120  # enough for the 60-session UI history without unbounded table growth
_CHECKPOINT_SESSIONS = 35
_BATCH = 1000
_MAX_FILE_BYTES = 32 * 1024 * 1024
_SOURCE = "finra_short_volume"
_HEADER = "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market"


def parse_cnms(text: str, *, expected_date: dt.date | None = None) -> list[dict]:
    """Parse and validate one complete FINRA CNMS file.

    The trailer is an integrity boundary. A truncated or newly incompatible file is rejected in
    full instead of being persisted as an apparently quiet market day.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3 or lines[0] != _HEADER:
        raise ValueError("invalid FINRA CNMS header")
    try:
        expected_records = int(lines[-1])
    except ValueError as exc:
        raise ValueError("invalid FINRA CNMS record-count trailer") from exc
    data_lines = lines[1:-1]
    if expected_records != len(data_lines):
        raise ValueError(
            f"FINRA CNMS record count mismatch: trailer={expected_records} lines={len(data_lines)}"
        )

    rows: list[dict] = []
    for line_number, line in enumerate(data_lines, start=2):
        parts = line.split("|")
        if len(parts) != 6:
            raise ValueError(f"invalid FINRA CNMS row at line {line_number}")
        try:
            date = dt.datetime.strptime(parts[0], "%Y%m%d").date()
            short_vol = Decimal(parts[2])
            exempt_vol = Decimal(parts[3])
            total_vol = Decimal(parts[4])
        except (ValueError, InvalidOperation) as exc:
            raise ValueError(f"invalid FINRA CNMS value at line {line_number}") from exc
        if expected_date is not None and date != expected_date:
            raise ValueError(
                f"FINRA CNMS date mismatch at line {line_number}: {date} != {expected_date}"
            )
        # SIP symbols are case-sensitive: e.g. BCpC (a preferred issue) and BCPC (common stock)
        # are different securities. Canonical product mapping happens later via security-master
        # aliases; changing case here would merge them and corrupt both records.
        code = parts[1].strip()
        if (
            not code
            or len(code) > 16
            or not all(value.is_finite() for value in (short_vol, exempt_vol, total_vol))
            or total_vol <= 0
            or short_vol < 0
            or exempt_vol < 0
            # FINRA defines ShortVolume as including ShortExemptVolume; exempt is a subset,
            # not an additional amount to add when calculating the short-sale share.
            or short_vol > total_vol
            or exempt_vol > short_vol
        ):
            raise ValueError(f"invalid FINRA CNMS volume relationship at line {line_number}")
        rows.append(
            {
                "market": MARKET,
                "code": code,
                "date": date,
                "short_volume": short_vol,
                "short_exempt_volume": exempt_vol,
                "total_volume": total_vol,
            }
        )
    return rows


def _build_symbol_aliases(
    securities: Iterable[SecurityMaster], known_codes: set[str]
) -> dict[str, str]:
    """Map exact source aliases to one canonical product code; omit ambiguous aliases."""
    candidates: dict[str, set[str]] = defaultdict(set)
    for code in known_codes:
        candidates[code].add(code)
    for security in securities:
        for alias in {
            security.symbol,
            security.raw_symbol,
            security.cqs_symbol,
            security.nasdaq_symbol,
        }:
            if alias:
                candidates[alias.strip()].add(security.symbol)
    return {
        alias: next(iter(codes))
        for alias, codes in candidates.items()
        if len(codes) == 1 and next(iter(codes)) in known_codes
    }


async def _fetch_day(
    client: httpx.AsyncClient, day: dt.date
) -> tuple[list[dict], int] | None:
    """Rows for one session, or None when FINRA hasn't published it (403/404 — routine)."""
    resp = await client.get(_URL.format(ymd=day.strftime("%Y%m%d")))
    if resp.status_code in {403, 404}:
        return None
    resp.raise_for_status()
    if len(resp.content) > _MAX_FILE_BYTES:
        raise ValueError(f"FINRA CNMS file exceeds {_MAX_FILE_BYTES} bytes")
    return parse_cnms(resp.text, expected_date=day), len(resp.content)


def _recent_sessions(now: dt.datetime, limit: int) -> list[dt.date]:
    """The most recent completed/likely-published US sessions, oldest first."""
    local = to_market_tz(now, market=MARKET)
    day = local.date()
    # Today's file exists only after the evening publish; include today and let 403 skip it early.
    out: list[dt.date] = []
    while len(out) < limit:
        if is_trading_day(day, market=MARKET):
            out.append(day)
        day -= dt.timedelta(days=1)
    return list(reversed(out))


async def collect(target: dt.date | None = None) -> dict[str, int]:
    """Ingest FINRA short volume for `target`, or today + any missing recent sessions."""
    sm = get_sessionmaker()
    async with sm() as session:
        known = set(await session.scalars(select(Symbol.code).where(Symbol.market == MARKET)))
        eligible_securities = list(
            await session.scalars(
                select(SecurityMaster).where(
                    SecurityMaster.market == MARKET,
                    SecurityMaster.is_product_eligible.is_(True),
                )
            )
        )
        aliases = _build_symbol_aliases(eligible_securities, known)
        state = await session.get(RegulatoryDataState, (MARKET, _SOURCE))
        completed_sessions = (
            dict((state.details or {}).get("completed_sessions") or {}) if state else {}
        )
        stored_sessions = set(
            await session.scalars(
                select(ShortVolumeDaily.date)
                .where(ShortVolumeDaily.market == MARKET)
                .distinct()
            )
        )
        if target is not None:
            days = [target]
        else:
            candidates = _recent_sessions(dt.datetime.now(dt.UTC), _CATCHUP_SESSIONS)
            days = [
                day
                for day in candidates
                if day not in stored_sessions and day.isoformat() not in completed_sessions
            ]

    stats = {
        "days_fetched": 0,
        "days_skipped": 0,
        "rows_upserted": 0,
        "rows_unknown_symbol": 0,
        "rows_pruned": 0,
    }
    if not days:
        return stats

    async with httpx.AsyncClient(
        headers={"User-Agent": _UA}, timeout=60, follow_redirects=True
    ) as client:
        for day in days:
            fetched = await _fetch_day(client, day)
            if fetched is None:
                stats["days_skipped"] += 1
                continue
            rows, downloaded_bytes = fetched
            keep = [{**row, "code": aliases[row["code"]]} for row in rows if row["code"] in aliases]
            canonical_keys = {(row["code"], row["date"]) for row in keep}
            if len(canonical_keys) != len(keep):
                raise ValueError(
                    f"multiple FINRA rows map to one canonical symbol for {day}; refusing file"
                )
            stats["rows_unknown_symbol"] += len(rows) - len(keep)
            async with sm() as session:
                for i in range(0, len(keep), _BATCH):
                    chunk = keep[i : i + _BATCH]
                    stmt = pg_insert(ShortVolumeDaily).values(chunk)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["market", "code", "date"],
                        set_={
                            "short_volume": stmt.excluded.short_volume,
                            "short_exempt_volume": stmt.excluded.short_exempt_volume,
                            "total_volume": stmt.excluded.total_volume,
                        },
                    )
                    await session.execute(stmt)
                current_state = await session.get(RegulatoryDataState, (MARKET, _SOURCE))
                completed_sessions = dict(
                    (current_state.details or {}).get("completed_sessions") or {}
                ) if current_state else {}
                completed_sessions[day.isoformat()] = {
                    "source_rows": len(rows),
                    "stored_rows": len(keep),
                    "unknown_symbols": len(rows) - len(keep),
                    "url": _URL.format(ymd=day.strftime("%Y%m%d")),
                }
                completed_sessions = dict(
                    sorted(completed_sessions.items())[-_CHECKPOINT_SESSIONS:]
                )
                pruned = await session.execute(
                    delete(ShortVolumeDaily).where(
                        ShortVolumeDaily.market == MARKET,
                        ShortVolumeDaily.date < day - dt.timedelta(days=_RETENTION_DAYS),
                    )
                )
                stats["rows_pruned"] += pruned.rowcount or 0
                total_records = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(ShortVolumeDaily)
                        .where(ShortVolumeDaily.market == MARKET)
                    )
                    or 0
                )
                state_row = {
                    "market": MARKET,
                    "source": _SOURCE,
                    "as_of_date": day,
                    "last_success_at": dt.datetime.now(dt.UTC),
                    "records": total_records,
                    "symbols_covered": len(keep),
                    "downloaded_bytes": downloaded_bytes,
                    "details": {
                        "dataset": "FINRA Reg SHO consolidated NMS daily short-sale volume",
                        "completed_sessions": completed_sessions,
                        "latest_source_rows": len(rows),
                        "latest_stored_rows": len(keep),
                        "retention_days": _RETENTION_DAYS,
                        "raw_files_retained": False,
                    },
                }
                state_stmt = pg_insert(RegulatoryDataState).values(state_row)
                await session.execute(
                    state_stmt.on_conflict_do_update(
                        index_elements=["market", "source"],
                        set_={
                            key: state_stmt.excluded[key]
                            for key in state_row
                            if key not in {"market", "source"}
                        },
                    )
                )
                await session.commit()
            stats["days_fetched"] += 1
            stats["rows_upserted"] += len(keep)
            log.info("finra_short ingested day=%s rows=%s", day, len(keep))
    return stats


def main() -> None:
    target = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None
    stats = asyncio.run(collect(target))
    print(f"[finra_short] done: {stats}")


if __name__ == "__main__":
    main()
