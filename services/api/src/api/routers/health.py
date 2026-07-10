"""Health + tenant-echo endpoints. Proves the scaffold runs end to end."""

from __future__ import annotations

import asyncio

import redis.asyncio as aioredis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from api.deps import CurrentTenant
from bulls.core.config import get_settings
from bulls.core.db import get_sessionmaker

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Backward-compatible process liveness probe."""
    return {"status": "ok"}


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> JSONResponse:
    """Dependency readiness for load balancers; never reports healthy on partial failure."""
    checks: dict[str, str] = {"database": "ok", "redis": "ok"}
    try:
        async with get_sessionmaker()() as session:
            await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=3)
    except Exception:
        checks["database"] = "unavailable"

    redis = aioredis.from_url(get_settings().redis_url)
    try:
        await asyncio.wait_for(redis.ping(), timeout=3)
    except Exception:
        checks["redis"] = "unavailable"
    finally:
        await redis.aclose()

    ready_now = all(value == "ok" for value in checks.values())
    return JSONResponse(
        status_code=200 if ready_now else 503,
        content={"status": "ready" if ready_now else "not_ready", "checks": checks},
    )


@router.get("/whoami")
async def whoami(tenant: CurrentTenant) -> dict[str, str]:
    """Echoes the resolved tenant — confirms multi-tenant routing works."""
    return {
        "tenant": tenant.name,
        "display_name": tenant.display_name,
        "market": tenant.market,
        "locale": tenant.locale,
    }
