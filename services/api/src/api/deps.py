"""Shared FastAPI dependencies: active tenant, db session, current user."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from bulls.core.config import get_settings
from bulls.core.db import get_session
from bulls.core.markets import get_market_profile
from bulls.core.models import Symbol, User
from bulls.core.security import decode_access_token_claims
from bulls.core.tenancy import Tenant


def current_tenant(request: Request) -> Tenant:
    return request.state.tenant


def selected_admin_tenant(
    request: Request,
    tenant: Annotated[str, Query(description="Explicit tenant name for an admin operation")],
) -> Tenant:
    """Resolve an admin-selected tenant by name; never fall back through request headers."""
    selected = request.app.state.tenants.get(tenant)
    if selected is None:
        raise HTTPException(status_code=404, detail=f"Unknown tenant: {tenant}")
    return selected


# Languages the portal renders generated content in. The client picks one (persisted) and sends it
# as `X-Locale`; we fall back to the tenant default when absent/unsupported.
SUPPORTED_LOCALES = {"en", "bn"}


def current_locale(
    tenant: Annotated[Tenant, Depends(current_tenant)],
    x_locale: Annotated[str | None, Header()] = None,
) -> str:
    if x_locale and x_locale.lower() in SUPPORTED_LOCALES:
        return x_locale.lower()
    return tenant.locale


def visible_codes(market: str) -> Select:
    """Subquery of codes a retail user should see: active and not admin-hidden."""
    return select(Symbol.code).where(
        Symbol.market == market,
        Symbol.is_active.is_(True),
        Symbol.is_hidden.is_(False),
        Symbol.data_status == "ready",
    )


def enforce_market_feature(tenant: Tenant, feature: str) -> None:
    """Fail closed when a tenant has not enabled a product capability."""
    features = get_market_profile(tenant.market).features
    if not getattr(features, feature, False):
        raise HTTPException(status_code=404, detail="Feature is not available for this market")


def require_admin(x_admin_token: Annotated[str | None, Header()] = None) -> None:
    """Guard admin routes with a shared token (ADMIN_TOKEN). No token configured = locked."""
    token = get_settings().admin_token
    # Constant-time comparison: response timing can never leak how much of the token matched.
    if not token or not secrets.compare_digest(x_admin_token or "", token):
        raise HTTPException(status_code=403, detail="Admin access required")


CurrentTenant = Annotated[Tenant, Depends(current_tenant)]
SelectedAdminTenant = Annotated[Tenant, Depends(selected_admin_tenant)]
CurrentLocale = Annotated[str, Depends(current_locale)]
DbSession = Annotated[AsyncSession, Depends(get_session)]

_bearer = HTTPBearer(auto_error=True)


async def current_user(
    tenant: CurrentTenant,
    session: DbSession,
    creds: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> User:
    claims = decode_access_token_claims(creds.credentials, tenant_id=tenant.name)
    subject = claims.get("sub") if claims else None
    user = await session.get(User, int(subject)) if subject and subject.isdigit() else None
    # cross-tenant guard: a token is only valid within its own tenant
    if (
        user is None
        or user.tenant_id != tenant.name
        or user.auth_version != claims.get("ver")
    ):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


CurrentUser = Annotated[User, Depends(current_user)]

_bearer_optional = HTTPBearer(auto_error=False)


async def optional_user(
    tenant: CurrentTenant,
    session: DbSession,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_optional)],
) -> User | None:
    """Like current_user, but returns None for anonymous callers instead of 401.

    Used by public reads (e.g. the feed) that personalize when a token is present — such as marking
    which posts the caller has reacted to — without requiring login.
    """
    if creds is None:
        return None
    claims = decode_access_token_claims(creds.credentials, tenant_id=tenant.name)
    subject = claims.get("sub") if claims else None
    user = await session.get(User, int(subject)) if subject and subject.isdigit() else None
    if (
        user is None
        or user.tenant_id != tenant.name
        or user.auth_version != claims.get("ver")
    ):
        return None
    return user


OptionalUser = Annotated[User | None, Depends(optional_user)]
