"""Official SEC ingestion scheduler, isolated from market-data provider workers."""

from __future__ import annotations

import logging
from typing import ClassVar

from arq import cron
from arq.connections import RedisSettings

from bulls.core.config import get_settings
from ingestion.sec import collect as refresh_sec_evidence
from ingestion.sec_13f import collect as refresh_sec_13f
from ingestion.signals.runner import run_sec_filing_agents, run_us_institutional_agent

log = logging.getLogger(__name__)
TENANT_ID = "bullsofwallst"


async def refresh_sec_company_data(ctx) -> str:
    stats = await refresh_sec_evidence()
    notes = await run_sec_filing_agents(tenant_id=TENANT_ID)
    log.info("sec_company_data_complete stats=%s notes=%s", stats, notes)
    return f"sec={stats} notes={notes}"


async def refresh_sec_institutional_data(ctx) -> str:
    stats = await refresh_sec_13f()
    notes = await run_us_institutional_agent(tenant_id=TENANT_ID)
    log.info("sec_13f_complete stats=%s notes=%s", stats, notes)
    return f"sec_13f={stats} notes={notes}"


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
        evaluate_stored_regulatory_agents,
    ]
    cron_jobs: ClassVar = [
        # Network/archive refreshes never run merely because code was deployed. On constrained
        # hosts, repeated 95+ MiB 13F archive parses can starve API and TLS workers.
        cron(refresh_sec_company_data, hour=6, minute=15, run_at_startup=False),
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
    job_timeout: ClassVar = 7200
