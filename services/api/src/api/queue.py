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
        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _pool


async def enqueue_sentiment(post_id: int) -> None:
    try:
        pool = await _get_pool()
        await pool.enqueue_job("tag_sentiment", post_id)
    except Exception as e:
        log.warning("sentiment enqueue failed for post %s: %s", post_id, e)


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
