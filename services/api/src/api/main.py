"""FastAPI app entry point.

Wires the tenant registry (loaded once at startup) into request state via middleware, so every
handler can read the active tenant. Run with:

    uv run granian --interface asgi api.main:app --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
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
    health,
    investor_lens,
    levels,
    market,
    moderation,
    news,
    plain_read,
    portfolio,
    posts,
    pulse,
    quiz,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.tenants = TenantRegistry.from_dir(_TENANTS_DIR, default=settings.default_tenant)
    yield
    await close_pool()
    await dispose_engine()


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
async def resolve_tenant(request: Request, call_next):
    registry: TenantRegistry = request.app.state.tenants
    request.state.tenant = registry.resolve(
        request.headers.get("host"),
        tenant_host=request.headers.get("x-tenant-host"),
        origin=request.headers.get("origin"),
        referer=request.headers.get("referer"),
    )
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Baseline hardening on every response (nginx terminates TLS; HSTS pins it in browsers)."""
    resp = await call_next(request)
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
app.include_router(admin.router)
app.include_router(admin_overview.router)
app.include_router(agents_admin.router)
app.include_router(auth.router)
app.include_router(buzz.router)
app.include_router(company.router)
app.include_router(desks.router)
app.include_router(digest.router)
app.include_router(explainer.router)
app.include_router(levels.router)
app.include_router(market.router)
app.include_router(moderation.router)
app.include_router(news.router)
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
