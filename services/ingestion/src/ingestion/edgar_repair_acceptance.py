"""Backfill missing EDGAR acceptance timestamps from the immutable archive.

Form 4 events were persisted with ``accepted_at = NULL`` because the value was only read on the
13D/G parse path. The fix is in ``edgar_events.parse_filing``; this repairs the rows already
captured under the old behaviour.

No filing is re-fetched from SEC. The raw dissemination bytes were archived content-addressed at
capture time precisely so a parsing defect could be corrected historically — this command is that
guarantee being cashed in. Rows whose archived bytes carry no usable header are left NULL rather
than filled with a guess.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from sqlalchemy import select, update

from bulls.core.db import get_sessionmaker
from bulls.core.models import EdgarFilingEvent
from bulls.market_data.providers.sec_daily_index import parse_acceptance_datetime

_MAX_FILING_BYTES = 50 * 1024 * 1024


async def repair(*, store, limit: int | None = None, dry_run: bool = False) -> dict[str, Any]:
    sessionmaker = get_sessionmaker()
    counts = {"examined": 0, "repaired": 0, "no_header": 0, "unreadable": 0, "dry_run": dry_run}
    async with sessionmaker() as session:
        query = (
            select(EdgarFilingEvent.accession_number, EdgarFilingEvent.raw_object_key)
            .where(
                EdgarFilingEvent.accepted_at.is_(None),
                EdgarFilingEvent.raw_object_key.is_not(None),
            )
            .order_by(EdgarFilingEvent.accession_number)
        )
        if limit is not None:
            query = query.limit(limit)
        rows = list(await session.execute(query))

        pending: list[tuple[str, Any]] = []
        for accession, key in rows:
            counts["examined"] += 1
            try:
                raw = store.get(key=key, max_bytes=_MAX_FILING_BYTES)
            except Exception:
                counts["unreadable"] += 1
                continue
            accepted_at = parse_acceptance_datetime(raw)
            if accepted_at is None:
                counts["no_header"] += 1
                continue
            pending.append((accession, accepted_at))

        if not dry_run:
            for index in range(0, len(pending), 1000):
                for accession, accepted_at in pending[index : index + 1000]:
                    await session.execute(
                        update(EdgarFilingEvent)
                        .where(EdgarFilingEvent.accession_number == accession)
                        .values(accepted_at=accepted_at)
                    )
                await session.commit()
        counts["repaired"] = len(pending)
    return counts


def main() -> None:
    from ingestion.us_options.storage import object_store

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    counts = asyncio.run(repair(store=object_store(), limit=args.limit, dry_run=args.dry_run))
    json.dump(counts, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
