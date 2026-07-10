"""Official SEC ingestion scheduler, isolated from market-data provider workers."""

from __future__ import annotations

import logging
from typing import ClassVar

from arq import cron
from arq.connections import RedisSettings

from bulls.core.config import get_settings
from ingestion.sec import collect as refresh_sec_evidence
from ingestion.sec_13f import collect as refresh_sec_13f

log = logging.getLogger(__name__)


async def refresh_sec_company_data(ctx) -> str:
    stats = await refresh_sec_evidence()
    log.info("sec_company_data_complete stats=%s", stats)
    return f"sec={stats}"


async def refresh_sec_institutional_data(ctx) -> str:
    stats = await refresh_sec_13f()
    log.info("sec_13f_complete stats=%s", stats)
    return f"sec_13f={stats}"


class WorkerSettings:
    functions: ClassVar = [refresh_sec_company_data, refresh_sec_institutional_data]
    cron_jobs: ClassVar = [
        cron(refresh_sec_company_data, hour=6, minute=15, run_at_startup=True),
        cron(refresh_sec_institutional_data, weekday="sun", hour=10, minute=0),
    ]
    redis_settings: ClassVar = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name: ClassVar = get_settings().sec_ingestion_queue_name
    max_jobs: ClassVar = 1
    job_timeout: ClassVar = 7200
