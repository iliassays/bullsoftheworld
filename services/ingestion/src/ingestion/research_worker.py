"""Explicit US research-preparation worker, isolated from scheduled market publication."""

from __future__ import annotations

from typing import ClassVar

from arq import cron
from arq.connections import RedisSettings

from bulls.core.config import get_settings
from ingestion.on_demand_research import (
    prepare_on_demand_research,
    reconcile_on_demand_research,
)


class WorkerSettings:
    functions: ClassVar = [prepare_on_demand_research]
    cron_jobs: ClassVar = [
        cron(
            reconcile_on_demand_research,
            minute=set(range(60)),
            second=15,
            run_at_startup=True,
        )
    ]
    redis_settings: ClassVar = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name: ClassVar = get_settings().us_research_queue_name
    # One preparation plus the lightweight durable-queue reconciler.
    max_jobs: ClassVar = 2
    max_tries: ClassVar = 3
    job_timeout: ClassVar = 7200
