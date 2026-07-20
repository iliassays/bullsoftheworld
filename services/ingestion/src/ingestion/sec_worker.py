"""Official SEC ingestion scheduler, isolated from market-data provider workers."""

from __future__ import annotations

import datetime as dt
import logging
from typing import ClassVar

from arq import cron
from arq.connections import RedisSettings

from bulls.core.config import get_settings
from ingestion.edgar_events import collect_day as collect_edgar_day
from ingestion.restricted_research import restricted_research_codes
from ingestion.sec import collect as refresh_sec_evidence
from ingestion.sec_13f import collect as refresh_sec_13f
from ingestion.signals.runner import run_sec_filing_agents, run_us_institutional_agent
from ingestion.us_options.storage import object_store

log = logging.getLogger(__name__)
TENANT_ID = "bullsofwallst"


async def refresh_sec_company_data(ctx) -> str:
    stats = await refresh_sec_evidence()
    try:
        restricted_codes = await restricted_research_codes()
        restricted = (
            await refresh_sec_evidence(codes=restricted_codes)
            if restricted_codes
            else {"symbols": 0}
        )
    except Exception as error:
        log.warning("restricted SEC refresh failed; public agents will continue", exc_info=True)
        restricted = {"failed": type(error).__name__}
    notes = await run_sec_filing_agents(tenant_id=TENANT_ID)
    log.info(
        "sec_company_data_complete stats=%s restricted=%s notes=%s",
        stats,
        restricted,
        notes,
    )
    return f"sec={stats} restricted={restricted} notes={notes}"


async def refresh_sec_institutional_data(ctx) -> str:
    stats = await refresh_sec_13f()
    notes = await run_us_institutional_agent(tenant_id=TENANT_ID)
    log.info("sec_13f_complete stats=%s notes=%s", stats, notes)
    return f"sec_13f={stats} notes={notes}"


async def collect_edgar_filing_events(ctx) -> str:
    """Capture yesterday's 13D/G + Form 4 stream from the EDGAR daily index.

    Yesterday (US/Eastern) is used because EDGAR's dissemination day closes at
    22:00 ET; by the 03:30 UTC run the previous day's index is complete. Idempotent:
    already-captured accessions are skipped, so a rerun only fills gaps.
    """
    day = (dt.datetime.now(dt.UTC) - dt.timedelta(hours=9)).date() - dt.timedelta(days=1)
    counts = await collect_edgar_day(day, store=object_store())
    log.info("edgar_filing_events_complete day=%s counts=%s", day, counts)
    return f"edgar_events day={day} {counts}"


async def evaluate_stored_regulatory_agents(ctx) -> str:
    """Cheap startup reconciliation over committed evidence; never downloads SEC archives."""
    filing_notes = await run_sec_filing_agents(tenant_id=TENANT_ID)
    institutional_notes = await run_us_institutional_agent(tenant_id=TENANT_ID)
    log.info(
        "stored_regulatory_agents_complete filings=%s institutional=%s",
        filing_notes,
        institutional_notes,
    )
    return f"filings={filing_notes} institutional={institutional_notes}"


class WorkerSettings:
    functions: ClassVar = [
        refresh_sec_company_data,
        refresh_sec_institutional_data,
        collect_edgar_filing_events,
        evaluate_stored_regulatory_agents,
    ]
    cron_jobs: ClassVar = [
        # Network/archive refreshes never run merely because code was deployed. On constrained
        # hosts, repeated 95+ MiB 13F archive parses can starve API and TLS workers.
        cron(refresh_sec_company_data, hour=6, minute=15, run_at_startup=False),
        # After EDGAR's dissemination day closes (22:00 ET); idempotent gap-filler.
        cron(collect_edgar_filing_events, hour=3, minute=30, run_at_startup=False),
        cron(refresh_sec_institutional_data, weekday="sun", hour=10, minute=0),
        # Startup only evaluates already-committed rows; dedupe makes this safe and inexpensive.
        cron(
            evaluate_stored_regulatory_agents,
            weekday="sun",
            hour=10,
            minute=30,
            run_at_startup=True,
        ),
    ]
    redis_settings: ClassVar = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name: ClassVar = get_settings().sec_ingestion_queue_name
    max_jobs: ClassVar = 1
    # One new official archive can contain several million holdings rows. Derived checkpoints
    # make retries resumable, but a first parse still needs a realistic bounded execution window.
    job_timeout: ClassVar = 21600
    # A deploy cancellation must not turn a large archive refresh into surprise startup work.
    # Freshness monitoring reports an interrupted run; the next cron window performs the retry.
    retry_jobs: ClassVar = False
