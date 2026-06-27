"""Lightweight Redis-backed rate limiting + brute-force protection for auth routes.

Two layers:
- per-IP throttle on login/register (stops scripted hammering from one source), and
- per-account failed-login lockout (stops targeted guessing against one handle).

Uses the shared Redis already configured for the app. Fails OPEN: if Redis is unreachable we let the
request through rather than lock everyone out (availability > a best-effort throttle).
"""

from __future__ import annotations

import logging

import redis.asyncio as aioredis
from fastapi import HTTPException, Request

from bulls.core.config import get_settings

log = logging.getLogger(__name__)


def client_ip(request: Request) -> str:
    """Real client IP behind nginx — first hop of X-Forwarded-For, else the socket peer."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _redis() -> aioredis.Redis:
    return aioredis.from_url(get_settings().redis_url)


async def throttle(bucket: str, *, limit: int, window_s: int) -> None:
    """Count a hit on `bucket`; raise 429 once more than `limit` hits land within `window_s`."""
    try:
        redis = _redis()
        try:
            key = f"rl:{bucket}"
            n = await redis.incr(key)
            if n == 1:
                await redis.expire(key, window_s)
            if n > limit:
                ttl = await redis.ttl(key)
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many attempts. Please try again in {max(ttl, 1)} seconds.",
                )
        finally:
            await redis.aclose()
    except HTTPException:
        raise
    except Exception:
        log.warning("rate-limit backend unavailable; allowing request", exc_info=True)


# --- per-account failed-login lockout ---------------------------------------
_FAIL_WINDOW_S = 900  # 15 minutes
_FAIL_MAX = 5  # lock after this many failures in the window


async def assert_not_locked(handle: str) -> None:
    """Block login attempts for a handle that has too many recent failures."""
    try:
        redis = _redis()
        try:
            n = await redis.get(f"rl:loginfail:{handle}")
            if n is not None and int(n) >= _FAIL_MAX:
                ttl = await redis.ttl(f"rl:loginfail:{handle}")
                raise HTTPException(
                    status_code=429,
                    detail=f"Account temporarily locked after repeated failures. Try again in {max(ttl, 1)} seconds.",
                )
        finally:
            await redis.aclose()
    except HTTPException:
        raise
    except Exception:
        log.warning("lockout check unavailable; allowing request", exc_info=True)


async def record_failure(handle: str) -> None:
    try:
        redis = _redis()
        try:
            key = f"rl:loginfail:{handle}"
            n = await redis.incr(key)
            if n == 1:
                await redis.expire(key, _FAIL_WINDOW_S)
        finally:
            await redis.aclose()
    except Exception:
        log.warning("failed-login record unavailable", exc_info=True)


async def reset_failures(handle: str) -> None:
    try:
        redis = _redis()
        try:
            await redis.delete(f"rl:loginfail:{handle}")
        finally:
            await redis.aclose()
    except Exception:
        pass
