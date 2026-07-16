"""Catalyst Calendar: collection and calendar reads for typed, tenant-shared catalyst events.

Collection projects already-ingested official records (DSE decoded announcements, US periodic
filing cadence) into `research_catalyst_events` under the normal forced-RLS tenant context. Reads
are side-effect free; status maintenance (marking past events `occurred`) happens during
collection so a read endpoint never mutates state.

    uv run python -m api.institutional_research.catalysts bullsofdhaka DSE
"""

from __future__ import annotations

import asyncio
import datetime as dt
import sys
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import case, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.institutional_research.schemas import CatalystCalendarOut, CatalystEventOut
from api.research_access import bind_research_tenant_context
from bulls.analytics.catalysts import (
    CatalystDraft,
    PeriodicFilingEvidence,
    dse_events_from_announcement,
    us_report_window_from_filings,
)
from bulls.core.db import get_sessionmaker
from bulls.core.models import Announcement, SecFiling, Symbol
from bulls.core.models.research import CatalystEvent

DSE_ANNOUNCEMENT_LOOKBACK_DAYS = 180
CALENDAR_PAST_GRACE_DAYS = 7
DSE_ANNOUNCEMENT_ARCHIVE_URL = "https://www.dsebd.org/old_news.php"


def _dse_announcement_url(published_at: dt.date) -> str:
    day = published_at.isoformat()
    return (
        f"{DSE_ANNOUNCEMENT_ARCHIVE_URL}?startDate={day}&endDate={day}"
        "&criteria=4&archive=news"
    )


def _catalyst_upsert_statement(rows: list[dict[str, Any]]):
    stmt = pg_insert(CatalystEvent).values(rows)
    return stmt.on_conflict_do_update(
        constraint="uq_research_catalyst_source_event",
        set_={
            "title": stmt.excluded.title,
            "timing_kind": stmt.excluded.timing_kind,
            "confirmed_date": stmt.excluded.confirmed_date,
            "window_start": stmt.excluded.window_start,
            "window_end": stmt.excluded.window_end,
            "status": case(
                (
                    CatalystEvent.status == "cancelled",
                    CatalystEvent.status,
                ),
                else_=stmt.excluded.status,
            ),
            "confidence": stmt.excluded.confidence,
            "source_type": stmt.excluded.source_type,
            "source_url": stmt.excluded.source_url,
            "known_at": stmt.excluded.known_at,
            "expected_evidence": stmt.excluded.expected_evidence,
            "details": stmt.excluded.details,
            "dedupe_key": stmt.excluded.dedupe_key,
            "updated_at": func.now(),
        },
    )


def _us_source_backfill_statement(tenant_id: str, market: str):
    filing_url = (
        select(SecFiling.filing_url)
        .where(
            SecFiling.market == CatalystEvent.market,
            SecFiling.code == CatalystEvent.code,
            SecFiling.accession_number == CatalystEvent.source_ref,
        )
        .limit(1)
        .scalar_subquery()
    )
    return (
        update(CatalystEvent)
        .where(
            CatalystEvent.tenant_id == tenant_id,
            CatalystEvent.market == market,
            CatalystEvent.source_type == "sec_filing_cadence",
            CatalystEvent.source_url.is_(None),
            filing_url.is_not(None),
        )
        .values(source_url=filing_url, updated_at=func.now())
    )


def _superseded_us_forecasts_statement(
    tenant_id: str,
    market: str,
    drafts: list[CatalystDraft],
):
    current_pairs = sorted(
        {
            (draft.code, draft.source_ref)
            for draft in drafts
            if draft.event_type == "periodic_report_window"
        }
    )
    if not current_pairs:
        return None
    current_codes = sorted({code for code, _ in current_pairs})
    return (
        update(CatalystEvent)
        .where(
            CatalystEvent.tenant_id == tenant_id,
            CatalystEvent.market == market,
            CatalystEvent.event_type == "periodic_report_window",
            CatalystEvent.status == "scheduled",
            CatalystEvent.code.in_(current_codes),
            tuple_(CatalystEvent.code, CatalystEvent.source_ref).not_in(current_pairs),
        )
        .values(status="cancelled", updated_at=func.now())
    )


async def _eligible_codes(session: AsyncSession, market: str) -> list[str]:
    return list(
        await session.scalars(
            select(Symbol.code).where(
                Symbol.market == market,
                Symbol.is_active.is_(True),
                Symbol.is_hidden.is_(False),
                Symbol.data_status.in_(("ready", "research_only")),
            )
        )
    )


async def _dse_drafts(session: AsyncSession, market: str, today: dt.date) -> list[CatalystDraft]:
    codes = set(await _eligible_codes(session, market))
    since = today - dt.timedelta(days=DSE_ANNOUNCEMENT_LOOKBACK_DAYS)
    announcements = await session.execute(
        select(
            Announcement.code,
            Announcement.published_at,
            Announcement.category,
            Announcement.headline,
            Announcement.details,
            Announcement.key,
        ).where(
            Announcement.market == market,
            Announcement.published_at >= since,
            Announcement.details.isnot(None),
        )
    )
    drafts: list[CatalystDraft] = []
    for code, published_at, category, headline, details, key in announcements:
        if code not in codes:
            continue
        drafts.extend(
            dse_events_from_announcement(
                market=market,
                code=code,
                published_at=published_at,
                category=category,
                headline=headline,
                details=details,
                source_ref=f"announcement:{key}",
                source_url=_dse_announcement_url(published_at),
            )
        )
    return drafts


async def _us_drafts(session: AsyncSession, market: str, today: dt.date) -> list[CatalystDraft]:
    codes = await _eligible_codes(session, market)
    if not codes:
        return []
    filings = await session.execute(
        select(
            SecFiling.code,
            SecFiling.form,
            SecFiling.filing_date,
            SecFiling.accession_number,
            SecFiling.accepted_at,
            SecFiling.filing_url,
        ).where(SecFiling.market == market, SecFiling.code.in_(codes))
    )
    by_code: dict[str, list[PeriodicFilingEvidence]] = defaultdict(list)
    for code, form, filing_date, accession, accepted_at, filing_url in filings:
        by_code[code].append(
            PeriodicFilingEvidence(
                form=form,
                filing_date=filing_date,
                accession_number=accession,
                accepted_at=accepted_at,
                source_url=filing_url,
            )
        )
    drafts: list[CatalystDraft] = []
    for code, history in by_code.items():
        draft = us_report_window_from_filings(
            market=market, code=code, periodic_filings=history, as_of=today
        )
        if draft is not None:
            drafts.append(draft)
    return drafts


async def collect_catalyst_events(
    *,
    tenant_id: str,
    market: str,
    user_id: int,
) -> dict[str, Any]:
    """Derive, upsert, and status-maintain catalyst events for one tenant/market."""
    today = dt.datetime.now(dt.UTC).date()
    sm = get_sessionmaker()
    async with sm() as session:
        await bind_research_tenant_context(
            session, tenant_id=tenant_id, market=market, user_id=user_id
        )
        if market == "DSE":
            drafts = await _dse_drafts(session, market, today)
        else:
            drafts = await _us_drafts(session, market, today)

        rows = []
        seen: set[tuple[str, str, str, str]] = set()
        for draft in drafts:
            identity = (draft.market, draft.code, draft.event_type, draft.source_ref)
            if identity in seen:
                continue
            seen.add(identity)
            key = draft.dedupe_key(tenant_id)
            ends_at = draft.confirmed_date or draft.window_end
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_id,
                    "dedupe_key": key,
                    "status": "occurred" if ends_at and ends_at < today else "scheduled",
                    **draft.model_dump(),
                }
            )
        if rows:
            await session.execute(_catalyst_upsert_statement(rows))

        backfilled_source_urls = 0
        superseded_forecasts = 0
        if market == "US":
            backfilled = await session.execute(_us_source_backfill_statement(tenant_id, market))
            backfilled_source_urls = int(backfilled.rowcount or 0)
            superseded_statement = _superseded_us_forecasts_statement(
                tenant_id,
                market,
                drafts,
            )
            if superseded_statement is not None:
                superseded = await session.execute(superseded_statement)
                superseded_forecasts = int(superseded.rowcount or 0)

        occurred = await session.execute(
            update(CatalystEvent)
            .where(
                CatalystEvent.tenant_id == tenant_id,
                CatalystEvent.market == market,
                CatalystEvent.status == "scheduled",
                (
                    (CatalystEvent.timing_kind == "confirmed")
                    & (CatalystEvent.confirmed_date < today)
                )
                | ((CatalystEvent.timing_kind == "window") & (CatalystEvent.window_end < today)),
            )
            .values(status="occurred")
        )
        await session.commit()
    return {
        "tenant_id": tenant_id,
        "market": market,
        "derived": len(drafts),
        "upserted": len(rows),
        "backfilled_source_urls": backfilled_source_urls,
        "superseded_forecasts": superseded_forecasts,
        "marked_occurred": int(occurred.rowcount or 0),
    }


async def load_catalyst_calendar(
    session: AsyncSession,
    *,
    tenant_id: str,
    market: str,
    workspace_id: uuid.UUID,
    horizon_days: int,
    code: str | None = None,
) -> CatalystCalendarOut:
    """Side-effect-free calendar read ordered by the earliest date an event can matter."""
    today = dt.datetime.now(dt.UTC).date()
    earliest = today - dt.timedelta(days=CALENDAR_PAST_GRACE_DAYS)
    latest = today + dt.timedelta(days=horizon_days)
    conditions = [
        CatalystEvent.tenant_id == tenant_id,
        CatalystEvent.market == market,
        (
            (CatalystEvent.timing_kind == "confirmed")
            & CatalystEvent.confirmed_date.between(earliest, latest)
        )
        | (
            (CatalystEvent.timing_kind == "window")
            & (CatalystEvent.window_end >= earliest)
            & (CatalystEvent.window_start <= latest)
        ),
    ]
    if code:
        conditions.append(CatalystEvent.code == code.upper())
    events = list(await session.scalars(select(CatalystEvent).where(*conditions)))
    events.sort(key=lambda event: (event.confirmed_date or event.window_start, event.code))
    return CatalystCalendarOut(
        tenant_id=tenant_id,
        market=market,
        workspace_id=workspace_id,
        generated_at=dt.datetime.now(dt.UTC),
        horizon_days=horizon_days,
        events=[CatalystEventOut.model_validate(event) for event in events],
    )


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python -m api.institutional_research.catalysts <tenant> <market>")
    result = asyncio.run(
        collect_catalyst_events(tenant_id=sys.argv[1], market=sys.argv[2].upper(), user_id=0)
    )
    print(result)


if __name__ == "__main__":
    main()
