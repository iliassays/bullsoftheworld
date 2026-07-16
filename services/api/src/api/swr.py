"""Shared stale-while-revalidate serving for expensive, shareable read models.

The pattern (screens, scanner radar): every successful build writes a freshness-keyed entry plus a
stable last-known-good copy. Reads serve the fresh entry when present; otherwise they serve the
last-known-good copy instantly and spawn exactly one background revalidation (a Redis NX lock
prevents stampedes). Only a true cold start computes in-request. Responses carry a Cache-Control
header so browsers and any CDN can reuse a copy briefly; each payload's own as-of timestamps stay
the freshness authority.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from fastapi import Response

log = logging.getLogger(__name__)

CACHE_CONTROL = "public, max-age=60, stale-while-revalidate=300"
# Bounds how long one revalidation claims the rebuild; anything longer has failed anyway.
REVALIDATE_LOCK_TTL = 240

_revalidation_tasks: set[asyncio.Task] = set()


def json_response(payload: bytes | str) -> Response:
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Cache-Control": CACHE_CONTROL},
    )


def spawn_revalidation(coro: Awaitable[None]) -> None:
    """Run one background revalidation without letting the task be garbage collected."""
    task = asyncio.create_task(coro)
    _revalidation_tasks.add(task)
    task.add_done_callback(_revalidation_tasks.discard)


async def serve_cached(
    redis,
    *,
    fresh_key: str,
    stale_key: str,
    revalidate: Callable[[], Awaitable[None]],
) -> Response | None:
    """Serve from cache under stale-while-revalidate; None means a cold start must build."""
    cached = await redis.get(fresh_key)
    if cached:
        # Serve the cached JSON bytes verbatim — skip the pydantic parse + re-serialize.
        return json_response(cached)
    stale = await redis.get(stale_key)
    if stale is None:
        return None
    lock_key = f"{stale_key}:revalidating"
    if await redis.set(lock_key, "1", nx=True, ex=REVALIDATE_LOCK_TTL):
        spawn_revalidation(_locked_revalidation(revalidate, lock_key))
    return json_response(stale)


async def _locked_revalidation(revalidate: Callable[[], Awaitable[None]], lock_key: str) -> None:
    import redis.asyncio as aioredis

    from bulls.core.config import get_settings

    try:
        await revalidate()
    except Exception:
        # The stale copy keeps serving; the lock expires on its own and the next request or
        # scheduled warm retries.
        log.exception("background revalidation failed for %s", lock_key)
        return
    redis = aioredis.from_url(get_settings().redis_url)
    try:
        await redis.delete(lock_key)
    finally:
        await redis.aclose()
