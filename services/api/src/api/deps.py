"""Shared FastAPI dependencies: active tenant + db session."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from bulls.core.db import get_session
from bulls.core.tenancy import Tenant


def current_tenant(request: Request) -> Tenant:
    return request.state.tenant


CurrentTenant = Annotated[Tenant, Depends(current_tenant)]
DbSession = Annotated[AsyncSession, Depends(get_session)]
