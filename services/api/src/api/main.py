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

from api.queue import close_pool
from api.routers import (
    auth,
    digest,
    explainer,
    health,
    market,
    posts,
    translate,
    trending,
    watchlist,
)
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
    request.state.tenant = registry.resolve(request.headers.get("host"))
    return await call_next(request)


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(digest.router)
app.include_router(explainer.router)
app.include_router(market.router)
app.include_router(posts.router)
app.include_router(translate.router)
app.include_router(trending.router)
app.include_router(watchlist.router)
