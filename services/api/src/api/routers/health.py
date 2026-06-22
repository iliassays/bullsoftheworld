"""Health + tenant-echo endpoints. Proves the scaffold runs end to end."""

from __future__ import annotations

from fastapi import APIRouter

from api.deps import CurrentTenant

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/whoami")
async def whoami(tenant: CurrentTenant) -> dict[str, str]:
    """Echoes the resolved tenant — confirms multi-tenant routing works."""
    return {
        "tenant": tenant.name,
        "display_name": tenant.display_name,
        "market": tenant.market,
        "locale": tenant.locale,
    }
