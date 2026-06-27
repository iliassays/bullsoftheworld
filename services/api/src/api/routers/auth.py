"""Auth: register, login, me. Handle-based, JWT bearer tokens."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

from api.deps import CurrentTenant, CurrentUser, DbSession
from api.ratelimit import (
    assert_not_locked,
    client_ip,
    record_failure,
    reset_failures,
    throttle,
)
from bulls.core.models import User
from bulls.core.schemas.social import LoginIn, RegisterIn, TokenOut, UserOut
from bulls.core.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
async def register(
    body: RegisterIn, request: Request, tenant: CurrentTenant, session: DbSession
) -> TokenOut:
    # Cap account creation from a single source (stops scripted signup floods).
    await throttle(f"register:{client_ip(request)}", limit=10, window_s=3600)
    handle = body.handle.strip().lower()  # handles are case-insensitive
    exists = await session.scalar(select(User).where(func.lower(User.handle) == handle))
    if exists is not None:
        raise HTTPException(status_code=409, detail="Handle already taken")
    user = User(
        tenant_id=tenant.name,
        handle=handle,
        name=body.name.strip(),
        password_hash=hash_password(body.password),
        locale=body.locale,
    )
    session.add(user)
    await session.flush()  # assign user.id before we mint the token
    return TokenOut(access_token=create_access_token(str(user.id)))


@router.post("/login")
async def login(
    body: LoginIn, request: Request, tenant: CurrentTenant, session: DbSession
) -> TokenOut:
    # Layer 1: throttle by source IP. Layer 2: lock the specific handle after repeated failures.
    await throttle(f"login:{client_ip(request)}", limit=20, window_s=300)
    handle = body.handle.strip().lower()
    await assert_not_locked(handle)

    user = await session.scalar(
        select(User).where(func.lower(User.handle) == handle, User.tenant_id == tenant.name)
    )
    if user is None or not verify_password(body.password, user.password_hash):
        await record_failure(handle)
        # Generic message — never reveal whether the handle exists or the password was wrong.
        raise HTTPException(status_code=401, detail="Invalid handle or password")
    await reset_failures(handle)
    return TokenOut(access_token=create_access_token(str(user.id)))


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
