"""Auth: register, login, me. Handle-based, JWT bearer tokens."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from api.deps import CurrentTenant, CurrentUser, DbSession
from bulls.core.models import User
from bulls.core.schemas.social import LoginIn, RegisterIn, TokenOut, UserOut
from bulls.core.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
async def register(body: RegisterIn, tenant: CurrentTenant, session: DbSession) -> TokenOut:
    exists = await session.scalar(select(User).where(User.handle == body.handle))
    if exists is not None:
        raise HTTPException(status_code=409, detail="Handle already taken")
    user = User(
        tenant_id=tenant.name,
        handle=body.handle,
        name=body.name,
        password_hash=hash_password(body.password),
        locale=body.locale,
    )
    session.add(user)
    await session.flush()  # assign user.id before we mint the token
    return TokenOut(access_token=create_access_token(str(user.id)))


@router.post("/login")
async def login(body: LoginIn, tenant: CurrentTenant, session: DbSession) -> TokenOut:
    user = await session.scalar(
        select(User).where(User.handle == body.handle, User.tenant_id == tenant.name)
    )
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid handle or password")
    return TokenOut(access_token=create_access_token(str(user.id)))


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
