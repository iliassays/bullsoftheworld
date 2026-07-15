"""arq enqueue helper for the API.

Enqueues jobs by name onto Redis; the ai_worker consumes them. Enqueuing is BEST-EFFORT — if
Redis is down or no worker is running, a post must still succeed. AI never blocks a request.
"""

from __future__ import annotations

import logging

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from bulls.core.config import get_settings

log = logging.getLogger(__name__)
_pool: ArqRedis | None = None
_us_pool: ArqRedis | None = None
_research_lifecycle_pool: ArqRedis | None = None


async def _get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await create_pool(
            RedisSettings.from_dsn(settings.redis_url),
            default_queue_name=settings.ai_queue_name,
        )
    return _pool


async def enqueue_sentiment(post_id: int) -> None:
    if get_settings().ai_provider == "disabled":
        return
    try:
        pool = await _get_pool()
        await pool.enqueue_job("tag_sentiment", post_id)
    except Exception as e:
        log.warning("sentiment enqueue failed for post %s: %s", post_id, e)


async def enqueue_moderation(post_id: int) -> None:
    """L4 safety+relevance screen (async, never blocks the post). Best-effort like sentiment."""
    try:
        pool = await _get_pool()
        await pool.enqueue_job("screen_post_safety", post_id)
    except Exception as e:
        log.warning("moderation enqueue failed for post %s: %s", post_id, e)


async def enqueue_post_embedding(post_id: int) -> None:
    """Index a published post for stock research retrieval. Best-effort, never blocks posting."""
    try:
        pool = await _get_pool()
        await pool.enqueue_job("embed_post", post_id)
    except Exception as e:
        log.warning("post embedding enqueue failed for post %s: %s", post_id, e)


async def enqueue_us_research_preparation(job_id: str, code: str, attempt: int) -> None:
    """Durably enqueue an explicitly requested US research preparation job."""
    global _us_pool
    if _us_pool is None:
        settings = get_settings()
        _us_pool = await create_pool(
            RedisSettings.from_dsn(settings.redis_url),
            default_queue_name=settings.us_research_queue_name,
        )
    queued = await _us_pool.enqueue_job(
        "prepare_on_demand_research",
        job_id,
        _job_id=f"research:US:{code}:{attempt}",
    )
    if queued is None:
        log.info("US research preparation already queued for %s", code)


async def enqueue_research_lifecycle(
    *,
    policy_id: str,
    workspace_id: str,
    tenant_id: str,
    market: str,
    user_id: int,
    trigger_key: str,
    job_id: str,
    scheduled: bool,
    defer_until=None,
) -> bool:
    """Enqueue one exact RLS identity envelope on the dedicated lifecycle queue."""

    global _research_lifecycle_pool
    if _research_lifecycle_pool is None:
        settings = get_settings()
        _research_lifecycle_pool = await create_pool(
            RedisSettings.from_dsn(settings.redis_url),
            default_queue_name=settings.research_lifecycle_queue_name,
        )
    queued = await _research_lifecycle_pool.enqueue_job(
        "run_research_lifecycle",
        policy_id,
        workspace_id,
        tenant_id,
        market,
        user_id,
        trigger_key,
        scheduled,
        _job_id=job_id,
        _defer_until=defer_until,
    )
    return queued is not None


async def close_pool() -> None:
    global _pool, _research_lifecycle_pool, _us_pool
    pools = (_pool, _us_pool, _research_lifecycle_pool)
    _pool, _us_pool, _research_lifecycle_pool = None, None, None
    for pool in pools:
        if pool is not None:
            await pool.aclose()
