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


async def close_pool() -> None:
    global _pool
    pool, _pool = _pool, None
    if pool is not None:
        await pool.aclose()
