"""Company reference + shareholding collection for DSE (displayCompany.php).

Slow-moving data — capital structure rarely changes, shareholding is monthly, dividends quarterly —
and each page is heavy (~330 KB) on a fragile source. So this is a WEEKLY low-concurrency sweep, not
part of the EOD cron. Per-symbol failures are skipped, not fatal.

Each symbol's profile is upserted (latest wins); shareholding snapshots accumulate as a time series
keyed by disclosure date. We also enrich the symbol row (sector/category) while we're here.

    uv run python -m ingestion.company            # all symbols (weekly)
    uv run python -m ingestion.company PRAGATIINS  # one symbol (debug)
"""

from __future__ import annotations

import asyncio
import datetime as dt
import sys

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.db import get_sessionmaker
from bulls.core.models import (
    AnnualFinancial,
    CompanyProfile,
    DividendRecord,
    SectorPE,
    ShareholdingSnapshot,
    Symbol,
)
from bulls.market_data import CompanyInfo, get_provider
from ingestion.lineage import record_company_data_observations

CONCURRENCY = 3  # gentle on a fragile source; heavier pages than the price endpoints
RETRIES = 3


async def _upsert_series(session, model, rows: list[dict], pk: tuple[str, ...]) -> None:
    """Upsert a list of rows for a time-series model, overwriting non-key columns on conflict."""
    if not rows:
        return
    stmt = pg_insert(model).values(rows)
    update_cols = {c: getattr(stmt.excluded, c) for c in rows[0] if c not in pk}
    if "first_seen_at" in update_cols:
        update_cols["first_seen_at"] = func.coalesce(
            model.first_seen_at,
            stmt.excluded.first_seen_at,
        )
    stmt = stmt.on_conflict_do_update(index_elements=list(pk), set_=update_cols)
    await session.execute(stmt)


async def _persist(session, info: CompanyInfo, fetched_at: dt.datetime) -> int:
    await record_company_data_observations(session, info, observed_at=fetched_at)
    profile = info.profile.model_dump()
    profile["fetched_at"] = fetched_at
    await _upsert_series(session, CompanyProfile, [profile], ("market", "code"))
    await _upsert_series(
        session,
        ShareholdingSnapshot,
        [dict(s.model_dump(), first_seen_at=fetched_at) for s in info.shareholdings],
        ("market", "code", "as_of_date"),
    )
    await _upsert_series(
        session,
        AnnualFinancial,
        [f.model_dump() for f in info.financials],
        ("market", "code", "fiscal_year"),
    )
    await _upsert_series(
        session,
        DividendRecord,
        [d.model_dump() for d in info.dividends],
        ("market", "code", "year"),
    )

    # Enrich the symbol universe (CLAUDE.md: names/sector come from company pages, not the price page).
    enrich = {
        k: v
        for k, v in (("sector", info.profile.sector), ("category", info.profile.market_category))
        if v
    }
    if enrich:
        await session.execute(
            update(Symbol)
            .where(Symbol.market == info.profile.market, Symbol.code == info.profile.code)
            .values(**enrich)
        )
    return len(info.shareholdings)


async def _collect_one(provider, code: str, fetched_at: dt.datetime) -> tuple[bool, int]:
    last_err: Exception | None = None
    for _ in range(RETRIES):
        try:
            info = await provider.get_company(code)
            if info is None:
                return (False, 0)
            sm = get_sessionmaker()
            async with sm() as session:
                n = await _persist(session, info, fetched_at)
                await session.commit()
            return (True, n)
        except Exception as e:
            last_err = e
            await asyncio.sleep(2)
    print(f"  ! {code}: giving up after {RETRIES} tries ({last_err})")
    return (False, 0)


async def _collect_sector_pe(provider, market: str, fetched_at: dt.datetime) -> int:
    """Refresh the sector-wide median P/E table (one small page, not per-symbol)."""
    try:
        sectors = await provider.get_sector_pe()
    except Exception as e:
        print(f"  ! sector P/E: skipped ({e})")
        return 0
    rows = [{**s.model_dump(), "fetched_at": fetched_at} for s in sectors]
    sm = get_sessionmaker()
    async with sm() as session:
        await _upsert_series(session, SectorPE, rows, ("market", "sector"))
        await session.commit()
    return len(rows)


async def collect(market: str, *, only: str | None = None) -> dict[str, int]:
    """Refresh company profiles + shareholding for every symbol (or just `only`). Returns stats."""
    provider = get_provider(market)
    if only:
        codes = [only]
    else:
        sm = get_sessionmaker()
        async with sm() as session:
            codes = list(await session.scalars(select(Symbol.code).where(Symbol.market == market)))

    fetched_at = dt.datetime.now(dt.UTC)
    sem = asyncio.Semaphore(CONCURRENCY)
    done = 0
    total = len(codes)

    async def one(code: str) -> tuple[bool, int]:
        nonlocal done
        async with sem:
            result = await _collect_one(provider, code, fetched_at)
            done += 1
            if done % 25 == 0 or done == total:
                print(f"  ...{done}/{total} symbols")
            return result

    results = await asyncio.gather(*(one(c) for c in codes))
    # Sector P/E is market-wide (one page); refresh it only on a full sweep, not single-symbol debug.
    sectors = 0 if only else await _collect_sector_pe(provider, market, fetched_at)
    return {
        "symbols": total,
        "profiles": sum(1 for ok, _ in results if ok),
        "shareholding_rows": sum(n for _, n in results),
        "sectors": sectors,
    }


def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"[company] refreshing DSE company data{f' for {only}' if only else ' (all symbols)'}")
    stats = asyncio.run(collect("DSE", only=only))
    print(f"[company] done: {stats}")


if __name__ == "__main__":
    main()
