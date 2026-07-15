"""Auth: register, login, refresh, me. Handle-based, JWT bearer + rotating refresh tokens.

Session model (fintech-standard): the access JWT lives 30 minutes; a 60-day opaque refresh token
(rotated on every use, reuse-detected, revocable) carries persistence. Presenting an already-
rotated refresh token revokes its whole family — the classic stolen-token replay defence."""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from api.deps import CurrentTenant, CurrentUser, DbSession
from api.emails import password_reset, verify_welcome
from api.identity import generate_handle, is_email, normalize_phone
from api.mailer import send_email
from api.ratelimit import (
    assert_not_locked,
    client_ip,
    record_failure,
    reset_failures,
    throttle,
)
from bulls.core.config import get_settings
from bulls.core.models import RefreshSession, User
from bulls.core.schemas.social import (
    ContactUpdateIn,
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
    decode_purpose_token_claims,
    hash_password,
    hash_refresh,
    new_refresh_token,
    verify_password,
)
from bulls.core.tenancy import Tenant

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)

_RESET_TTL_MIN = 30
_VERIFY_TTL_MIN = 60 * 24


def _link(tenant: Tenant, path: str, token: str, locale: str | None = None) -> str:
    """Return a canonical, tenant-localized account-action URL."""
    language = locale if locale in tenant.supported_locales else tenant.locale
    query = urlencode({"token": token})
    return f"{tenant.site_url.rstrip('/')}/{language}{path}?{query}"


async def _issue_tokens(
    session, user: User, request: Request, *, family: str | None = None
) -> TokenOut:
    """Mint the access+refresh pair; persist only the refresh hash."""
    raw = new_refresh_token()
    session.add(
        RefreshSession(
            user_id=user.id,
            token_hash=hash_refresh(raw),
            family=family or uuid.uuid4().hex,
            expires_at=dt.datetime.now(dt.UTC)
            + dt.timedelta(days=get_settings().refresh_token_ttl_days),
            user_agent=(request.headers.get("user-agent") or "")[:256] or None,
            ip=client_ip(request),
        )
    )
    await session.flush()
    return TokenOut(
        access_token=create_access_token(
            str(user.id), user.tenant_id, version=user.auth_version
        ),
        refresh_token=raw,
    )


async def _revoke_all_sessions(session, user_id: int) -> None:
    """Kill every live refresh session — used on password reset (and available for 'log out everywhere')."""
    await session.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )


class RefreshIn(BaseModel):
    refresh_token: str | None = None


def _refresh_value(body: RefreshIn, request: Request) -> str | None:
    settings = get_settings()
    return body.refresh_token or request.cookies.get(settings.refresh_cookie_name)


def _browser_tokens(response: Response, tokens: TokenOut) -> TokenOut:
    """Store refresh credentials outside JavaScript in production; retain a dev fallback."""
    if not tokens.refresh_token:
        return tokens
    settings = get_settings()
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=tokens.refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.production_cookies,
        samesite=settings.refresh_cookie_samesite,
        path="/auth",
    )
    if settings.production_cookies:
        return tokens.model_copy(update={"refresh_token": None})
    return tokens


async def _flush_identity(session) -> None:
    """Turn concurrent tenant-identity uniqueness races into a stable API conflict."""
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="That account identifier is already in use") from exc


@router.post("/refresh")
async def refresh(
    body: RefreshIn,
    request: Request,
    response: Response,
    tenant: CurrentTenant,
    session: DbSession,
) -> TokenOut:
    """Rotate the refresh token and mint a fresh access token.

    Reuse detection: a token that was already rotated (or revoked) coming back means replay —
    the entire family dies, forcing a real re-login on every device that shared the chain."""
    await throttle(f"refresh:{client_ip(request)}", limit=60, window_s=300)
    now = dt.datetime.now(dt.UTC)
    raw_refresh = _refresh_value(body, request)
    if not raw_refresh:
        raise HTTPException(status_code=401, detail="Session expired — please log in again.")
    row = await session.scalar(
        select(RefreshSession)
        .where(RefreshSession.token_hash == hash_refresh(raw_refresh))
        .with_for_update()
    )
    if row is None:
        raise HTTPException(status_code=401, detail="Session expired — please log in again.")
    if row.revoked_at is not None or row.replaced_by_id is not None:
        await session.execute(
            update(RefreshSession)
            .where(RefreshSession.family == row.family, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=func.now())
        )
        # Commit BEFORE raising — the error response would otherwise roll back the family
        # kill, leaving the attacker's rotated token alive. (Caught by the DB-gated test.)
        await session.commit()
        raise HTTPException(status_code=401, detail="Session expired — please log in again.")
    if row.expires_at <= now:
        raise HTTPException(status_code=401, detail="Session expired — please log in again.")

    user = await session.get(User, row.user_id)
    if user is None or user.tenant_id != tenant.name:
        row.revoked_at = now
        raise HTTPException(status_code=401, detail="Session expired — please log in again.")
    out = await _issue_tokens(session, user, request, family=row.family)
    new_row = await session.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == hash_refresh(out.refresh_token))
    )
    row.revoked_at = now
    row.replaced_by_id = new_row.id if new_row else None
    row.last_used_at = now
    return _browser_tokens(response, out)


@router.post("/logout")
async def logout(
    body: RefreshIn,
    request: Request,
    response: Response,
    tenant: CurrentTenant,
    session: DbSession,
) -> dict[str, str]:
    """Revoke this device's refresh session (the client drops the access token itself)."""
    raw_refresh = _refresh_value(body, request)
    row = await session.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == hash_refresh(raw_refresh))
    ) if raw_refresh else None
    if row is not None and row.revoked_at is None:
        user = await session.get(User, row.user_id)
        if user is not None and user.tenant_id == tenant.name:
            row.revoked_at = dt.datetime.now(dt.UTC)
    response.delete_cookie(get_settings().refresh_cookie_name, path="/auth")
    return {"status": "ok"}


@router.post("/register", status_code=201)
async def register(
    body: RegisterIn,
    request: Request,
    response: Response,
    tenant: CurrentTenant,
    session: DbSession,
) -> TokenOut:
    # Cap account creation from a single source (stops scripted signup floods).
    await throttle(f"register:{client_ip(request)}", limit=10, window_s=3600)

    # One contact field: email OR phone. Handle is generated from the name.
    contact = body.contact.strip()
    email: str | None = None
    phone: str | None = None
    if is_email(contact):
        email = contact.lower()
    else:
        phone = normalize_phone(contact)
        if phone is None:
            raise HTTPException(status_code=400, detail="Enter a valid email or phone number")
    if email and await session.scalar(
        select(User.id).where(User.tenant_id == tenant.name, User.email == email)
    ):
        raise HTTPException(
            status_code=409, detail="This email is already registered — please log in"
        )
    if phone and await session.scalar(
        select(User.id).where(User.tenant_id == tenant.name, User.phone == phone)
    ):
        raise HTTPException(
            status_code=409, detail="This phone is already registered — please log in"
        )

    user = User(
        tenant_id=tenant.name,
        handle=await generate_handle(session, tenant.name, body.name, email, phone),
        name=body.name.strip(),
        email=email,
        phone=phone,
        password_hash=hash_password(body.password),
        locale=body.locale,
    )
    session.add(user)
    await _flush_identity(session)  # assign user.id before we mint tokens

    # Welcome + email confirmation (only if they gave an email; best-effort — never blocks signup).
    if email:
        try:
            token = create_purpose_token(
                str(user.id),
                "verify",
                _VERIFY_TTL_MIN,
                tenant_id=tenant.name,
                email=email,
            )
            subject, html, text = verify_welcome(
                user.name,
                _link(tenant, "/verify", token, user.locale),
                user.locale,
                tenant,
            )
            await send_email(email, subject, html, text, tenant=tenant)
        except Exception:
            log.exception("welcome/verify email failed for %s", email)

    return _browser_tokens(response, await _issue_tokens(session, user, request))


@router.post("/login")
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    tenant: CurrentTenant,
    session: DbSession,
) -> TokenOut:
    # Layer 1: throttle by source IP. Layer 2: lock the specific identifier after repeated failures.
    await throttle(f"login:{client_ip(request)}", limit=20, window_s=300)
    ident = body.identifier.strip()
    key = f"{tenant.name}:{ident.lower()}"
    await assert_not_locked(key)

    # Match the identifier as email, phone, or auto-handle.
    if is_email(ident):
        cond = User.email == ident.lower()
    elif (ph := normalize_phone(ident)) is not None:
        cond = User.phone == ph
    else:
        cond = func.lower(User.handle) == ident.lower()
    user = await session.scalar(select(User).where(cond, User.tenant_id == tenant.name))

    if user is None or not verify_password(body.password, user.password_hash):
        await record_failure(key)
        # Generic message — never reveal whether the account exists or the password was wrong.
        raise HTTPException(status_code=401, detail="Invalid login or password")
    await reset_failures(key)
    return _browser_tokens(response, await _issue_tokens(session, user, request))


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
            token = create_purpose_token(
                str(user.id),
                "reset",
                _RESET_TTL_MIN,
                tenant_id=tenant.name,
                version=user.auth_version,
                email=user.email,
            )
            subject, html, text = password_reset(
                user.name,
                _link(tenant, "/reset", token, user.locale),
                user.locale,
                tenant,
            )
            await send_email(email, subject, html, text, tenant=tenant)
        except Exception:
            log.exception("reset email failed for %s", email)
    return {"status": "sent"}


@router.post("/reset")
async def reset_password(
    body: ResetIn,
    request: Request,
    response: Response,
    tenant: CurrentTenant,
    session: DbSession,
) -> TokenOut:
    """Consume a reset token and set a new password; log the user straight in."""
    claims = decode_purpose_token_claims(body.token, "reset", tenant_id=tenant.name)
    uid = claims.get("sub") if claims else None
    user = (
        await session.get(User, int(uid), with_for_update=True)
        if uid and uid.isdigit()
        else None
    )
    token_version = claims.get("ver", 0) if claims else None
    if (
        user is None
        or user.tenant_id != tenant.name
        or token_version != user.auth_version
        or claims.get("email") != user.email
    ):
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
    user.password_hash = hash_password(body.password)
    user.email_verified = True  # using the emailed link also proves the address
    user.auth_version += 1
    # A password reset means the old credentials can't be trusted — every session dies.
    await _revoke_all_sessions(session, user.id)
    await session.flush()
    return _browser_tokens(response, await _issue_tokens(session, user, request))


@router.post("/verify")
async def verify_email(
    body: VerifyIn, tenant: CurrentTenant, session: DbSession
) -> dict[str, str]:
    claims = decode_purpose_token_claims(body.token, "verify", tenant_id=tenant.name)
    uid = claims.get("sub") if claims else None
    user = await session.get(User, int(uid)) if uid and uid.isdigit() else None
    if (
        user is None
        or user.tenant_id != tenant.name
        or claims.get("email") != user.email
    ):
        raise HTTPException(status_code=400, detail="This link is invalid or has expired.")
    user.email_verified = True
    await session.flush()
    return {"status": "verified"}


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


async def _send_verify(user: User, tenant: Tenant) -> None:
    """Best-effort verification email (never raises)."""
    try:
        token = create_purpose_token(
            str(user.id),
            "verify",
            _VERIFY_TTL_MIN,
            tenant_id=user.tenant_id,
            email=user.email,
        )
        subject, html, text = verify_welcome(
            user.name,
            _link(tenant, "/verify", token, user.locale),
            user.locale,
            tenant,
        )
        await send_email(user.email, subject, html, text, tenant=tenant)
    except Exception:
        log.exception("verify email failed for %s", user.email)


@router.patch("/me")
async def update_contact(
    body: ContactUpdateIn,
    user: CurrentUser,
    tenant: CurrentTenant,
    session: DbSession,
) -> UserOut:
    """Add or change email / phone after signup. Changing a contact resets its verified flag."""
    send_verification = False
    if body.email is not None:
        email = body.email.strip().lower()
        if not is_email(email):
            raise HTTPException(status_code=400, detail="Enter a valid email")
        if email != user.email:
            if await session.scalar(
                select(User.id).where(
                    User.tenant_id == user.tenant_id,
                    User.email == email,
                    User.id != user.id,
                )
            ):
                raise HTTPException(status_code=409, detail="This email is already in use")
            user.email = email
            user.email_verified = False
            send_verification = True
    if body.phone is not None:
        phone = normalize_phone(body.phone)
        if phone is None:
            raise HTTPException(status_code=400, detail="Enter a valid phone number")
        if phone != user.phone:
            if await session.scalar(
                select(User.id).where(
                    User.tenant_id == user.tenant_id,
                    User.phone == phone,
                    User.id != user.id,
                )
            ):
                raise HTTPException(status_code=409, detail="This phone is already in use")
            user.phone = phone
            user.phone_verified = False  # phone OTP verification is a later phase
    await _flush_identity(session)
    if send_verification:
        await _send_verify(user, tenant)
    return UserOut.model_validate(user)


@router.post("/resend-verify", status_code=202)
async def resend_verify(
    user: CurrentUser, request: Request, tenant: CurrentTenant
) -> dict[str, str]:
    """Re-send the email verification link to the user's current (unverified) email."""
    await throttle(f"verify:{tenant.name}:{client_ip(request)}", limit=5, window_s=900)
    if user.email and not user.email_verified:
        await _send_verify(user, tenant)
    return {"status": "sent"}
