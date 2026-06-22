"""Shared FastAPI dependencies: active tenant, db session, current user."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from bulls.core.db import get_session
from bulls.core.models import User
from bulls.core.security import decode_token
from bulls.core.tenancy import Tenant


def current_tenant(request: Request) -> Tenant:
    return request.state.tenant


CurrentTenant = Annotated[Tenant, Depends(current_tenant)]
DbSession = Annotated[AsyncSession, Depends(get_session)]

_bearer = HTTPBearer(auto_error=True)


async def current_user(
    tenant: CurrentTenant,
    session: DbSession,
    creds: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> User:
    subject = decode_token(creds.credentials)
    user = await session.get(User, int(subject)) if subject and subject.isdigit() else None
    # cross-tenant guard: a token is only valid within its own tenant
    if user is None or user.tenant_id != tenant.name:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
