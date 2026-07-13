"""FastAPI app entry point.

Wires the tenant registry (loaded once at startup) into request state via middleware, so every
handler can read the active tenant. Run with:

    uv run granian --interface asgi api.main:app --port 8000
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.queue import close_pool
from api.routers import (
    admin,
    admin_overview,
    agents_admin,
    alerts,
    auth,
    buzz,
    company,
    desks,
    digest,
    explainer,
    growth,
    health,
    investor_lens,
    levels,
    market,
    moderation,
    news,
    on_demand_research,
    plain_read,
    portfolio,
    posts,
    pulse,
    quiz,
    regulatory,
    research,
    scanner,
    scorecard,
    screener,
    trending,
    users,
    views,
    watchlist,
)
from api.seo.router import router as seo_router
from bulls.core.config import get_settings
from bulls.core.db import dispose_engine
from bulls.core.tenancy import TenantRegistry

# tenants/ lives at the repo root: services/api/src/api/main.py -> up 5 -> repo root
_TENANTS_DIR = Path(__file__).resolve().parents[4] / "tenants"
log = logging.getLogger("api.requests")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lifespan owns the API pool. This also makes repeated in-process app starts deterministic
    # (test runners and ASGI reloaders can otherwise inherit a pool bound to a previous event loop).
    await dispose_engine()
    settings = get_settings()
    app.state.tenants = TenantRegistry.from_dir(_TENANTS_DIR, default=settings.default_tenant)
    yield
    for name, closer in (("queue", close_pool), ("database", dispose_engine)):
        try:
            async with asyncio.timeout(10):
                await closer()
        except TimeoutError:
            # The process is exiting; bound graceful shutdown instead of blocking deployment for
            # systemd's full stop timeout on a stale network connection.
            log.error("timed out closing %s resources during shutdown", name)


app = FastAPI(title="Bulls of the World API", lifespan=lifespan)

# Compress JSON responses (the /screens payload is ~65KB → ~10KB gzip'd). Only kicks in for clients
# that send Accept-Encoding: gzip (every browser) and responses over the threshold.
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Propagate a bounded request ID and emit one latency record per request."""
    supplied = request.headers.get("x-request-id", "")
    request_id = supplied if 0 < len(supplied) <= 128 else uuid.uuid4().hex
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    tenant = getattr(request.state, "tenant", None)
    log.info(
        "request_complete method=%s path=%s status=%s duration_ms=%s tenant=%s request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        tenant.name if tenant else "unresolved",
        request_id,
    )
    return response


@app.middleware("http")
async def resolve_tenant(request: Request, call_next):
    registry: TenantRegistry = request.app.state.tenants
    x_tenant_host = request.headers.get("x-tenant-host")
    tenant = registry.resolve_known(
        request.headers.get("host"),
        tenant_host=x_tenant_host,
        origin=request.headers.get("origin"),
        referer=request.headers.get("referer"),
    )
    # Tripwire for the 2026-07-13 cross-tenant leak's failure mode: a caller explicitly named a
    # tenant via X-Tenant-Host, but the resolved tenant is a different one — meaning some other
    # signal (almost always a Host header on a domain shared by more than one tenant's frontend,
    # e.g. this API's own hostname) outranked it. That should never happen; log loudly if it does
    # instead of silently serving the wrong tenant's content again.
    if x_tenant_host:
        claimed = registry.resolve_known(None, tenant_host=x_tenant_host)
        if claimed is not None and tenant is not None and claimed.name != tenant.name:
            log.warning(
                "tenant_resolution_mismatch host=%s x_tenant_host=%s resolved=%s claimed=%s",
                request.headers.get("host"),
                x_tenant_host,
                tenant.name,
                claimed.name,
            )
    settings = get_settings()
    local_env = settings.env.lower() in {"local", "dev", "development", "test"}
    probe = request.url.path in {"/health", "/live", "/ready"}
    if tenant is None and settings.strict_tenant_resolution and not local_env and not probe:
        return JSONResponse(
            status_code=421,
            content={"detail": "Request host does not map to a configured tenant"},
        )
    request.state.tenant = tenant or registry.resolve(request.headers.get("host"))
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Baseline hardening on every response (nginx terminates TLS; HSTS pins it in browsers)."""
    resp = await call_next(request)
    vary = {part.strip() for part in resp.headers.get("Vary", "").split(",") if part.strip()}
    vary.update({"Origin", "X-Tenant-Host", "Referer"})
    resp.headers["Vary"] = ", ".join(sorted(vary))
    # The API is tenant-sensitive. Let Redis/app-level caches handle reuse; HTTP intermediaries must
    # not serve a response resolved for one tenant to another tenant.
    resp.headers.setdefault("Cache-Control", "no-store")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return resp


# Serve generated card images (agent cards, e.g. Evening Wrap) referenced from feed posts.
_card_dir = Path(get_settings().card_dir)
_card_dir.mkdir(parents=True, exist_ok=True)
app.mount("/cards", StaticFiles(directory=_card_dir), name="cards")


app.include_router(alerts.router)
app.include_router(health.router)
app.include_router(investor_lens.router)
app.include_router(portfolio.router)
app.include_router(quiz.router)
app.include_router(regulatory.router)
app.include_router(admin.router)
app.include_router(admin_overview.router)
app.include_router(agents_admin.router)
app.include_router(auth.router)
app.include_router(buzz.router)
app.include_router(company.router)
app.include_router(desks.router)
app.include_router(digest.router)
app.include_router(explainer.router)
app.include_router(growth.router)
app.include_router(levels.router)
app.include_router(market.router)
app.include_router(moderation.router)
app.include_router(news.router)
app.include_router(on_demand_research.router)
app.include_router(plain_read.router)
app.include_router(posts.router)
app.include_router(pulse.router)
app.include_router(research.router)
app.include_router(scanner.router)
app.include_router(scorecard.router)
app.include_router(screener.router)
app.include_router(seo_router)
app.include_router(trending.router)
app.include_router(users.router)
app.include_router(views.router)
app.include_router(watchlist.router)
