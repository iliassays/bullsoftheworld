"""Auth: register, login, me. Handle-based, JWT bearer tokens."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

from api.deps import CurrentTenant, CurrentUser, DbSession
from api.emails import password_reset, verify_welcome
from api.mailer import send_email
from api.ratelimit import (
    assert_not_locked,
    client_ip,
    record_failure,
    reset_failures,
    throttle,
)
from bulls.core.config import get_settings
from bulls.core.models import User
from bulls.core.schemas.social import (
    ForgotIn,
    LoginIn,
    RegisterIn,
    ResetIn,
    TokenOut,
    UserOut,
    VerifyIn,
)
from bulls.core.security import (
    create_access_token,
    create_purpose_token,
    decode_purpose_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)

_RESET_TTL_MIN = 30
_VERIFY_TTL_MIN = 60 * 24


def _link(path: str, token: str) -> str:
    return f"{get_settings().app_base_url.rstrip('/')}{path}?token={token}"


@router.post("/register", status_code=201)
async def register(
    body: RegisterIn, request: Request, tenant: CurrentTenant, session: DbSession
) -> TokenOut:
    # Cap account creation from a single source (stops scripted signup floods).
    await throttle(f"register:{client_ip(request)}", limit=10, window_s=3600)
    handle = body.handle.strip().lower()  # handles are case-insensitive
    email = body.email.strip().lower()
    if await session.scalar(select(User).where(func.lower(User.handle) == handle)):
        raise HTTPException(status_code=409, detail="Handle already taken")
    if await session.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        tenant_id=tenant.name,
        handle=handle,
        name=body.name.strip(),
        email=email,
        password_hash=hash_password(body.password),
        locale=body.locale,
    )
    session.add(user)
    await session.flush()  # assign user.id before we mint tokens

    # Welcome + email confirmation (best-effort — never block signup on mail).
    try:
        token = create_purpose_token(str(user.id), "verify", _VERIFY_TTL_MIN)
        subject, html, text = verify_welcome(user.name, _link("/verify", token), user.locale)
        await send_email(email, subject, html, text)
    except Exception:
        log.exception("welcome/verify email failed for %s", email)

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


@router.post("/forgot", status_code=202)
async def forgot_password(
    body: ForgotIn, request: Request, tenant: CurrentTenant, session: DbSession
) -> dict[str, str]:
    """Email a time-limited reset link. Always returns 202 (never reveals whether the email exists)."""
    await throttle(f"forgot:{client_ip(request)}", limit=5, window_s=900)
    email = body.email.strip().lower()
    user = await session.scalar(
        select(User).where(User.email == email, User.tenant_id == tenant.name)
    )
    if user is not None:
        try:
            token = create_purpose_token(str(user.id), "reset", _RESET_TTL_MIN)
            subject, html, text = password_reset(user.name, _link("/reset", token), user.locale)
            await send_email(email, subject, html, text)
        except Exception:
            log.exception("reset email failed for %s", email)
    return {"status": "sent"}


@router.post("/reset")
async def reset_password(body: ResetIn, session: DbSession) -> TokenOut:
    """Consume a reset token and set a new password; log the user straight in."""
    uid = decode_purpose_token(body.token, "reset")
    user = await session.get(User, int(uid)) if uid and uid.isdigit() else None
    if user is None:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
    user.password_hash = hash_password(body.password)
    user.email_verified = True  # using the emailed link also proves the address
    await session.flush()
    return TokenOut(access_token=create_access_token(str(user.id)))


@router.post("/verify")
async def verify_email(body: VerifyIn, session: DbSession) -> dict[str, str]:
    uid = decode_purpose_token(body.token, "verify")
    user = await session.get(User, int(uid)) if uid and uid.isdigit() else None
    if user is None:
        raise HTTPException(status_code=400, detail="This link is invalid or has expired.")
    user.email_verified = True
    await session.flush()
    return {"status": "verified"}


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
