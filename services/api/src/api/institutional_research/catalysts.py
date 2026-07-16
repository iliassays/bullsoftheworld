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

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.institutional_research.schemas import CatalystCalendarOut, CatalystEventOut
from api.research_access import bind_research_tenant_context
from bulls.analytics.catalysts import (
    CatalystDraft,
    dse_events_from_announcement,
    us_report_window_from_filings,
)
from bulls.core.db import get_sessionmaker
from bulls.core.models import Announcement, SecFiling, Symbol
from bulls.core.models.research import CatalystEvent

DSE_ANNOUNCEMENT_LOOKBACK_DAYS = 180
CALENDAR_PAST_GRACE_DAYS = 7


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
            )
        )
    return drafts


async def _us_drafts(session: AsyncSession, market: str, today: dt.date) -> list[CatalystDraft]:
    codes = await _eligible_codes(session, market)
    if not codes:
        return []
    filings = await session.execute(
        select(
            SecFiling.code, SecFiling.form, SecFiling.filing_date, SecFiling.accession_number
        ).where(SecFiling.market == market, SecFiling.code.in_(codes))
    )
    by_code: dict[str, list[tuple[str, dt.date, str]]] = defaultdict(list)
    for code, form, filing_date, accession in filings:
        by_code[code].append((form, filing_date, accession))
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
        seen: set[str] = set()
        for draft in drafts:
            key = draft.dedupe_key(tenant_id)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_id,
                    "dedupe_key": key,
                    **draft.model_dump(),
                }
            )
        if rows:
            stmt = pg_insert(CatalystEvent).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["dedupe_key"],
                set_={
                    "title": stmt.excluded.title,
                    "expected_evidence": stmt.excluded.expected_evidence,
                    "details": stmt.excluded.details,
                    "source_url": stmt.excluded.source_url,
                },
            )
            await session.execute(stmt)

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
