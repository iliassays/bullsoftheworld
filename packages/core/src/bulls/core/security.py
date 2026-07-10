"""Auth helpers: password hashing + JWT + opaque refresh tokens."""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
from typing import Any

import bcrypt
import jwt

from bulls.core.config import get_settings

_TOKEN_ISSUER = "bullsoftheworld"
_TOKEN_AUDIENCE = "bulls-api"


def new_refresh_token() -> str:
    """Opaque 384-bit URL-safe token — never a JWT, carries nothing, means nothing off-server."""
    return secrets.token_urlsafe(48)


def hash_refresh(token: str) -> str:
    """Only this hash is persisted; a DB leak alone can't replay sessions."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _to_bytes(password: str) -> bytes:
    # bcrypt only considers the first 72 bytes; truncate explicitly so longer
    # passwords don't raise on bcrypt >= 4.1.
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(_to_bytes(password), hashed.encode("utf-8"))


def create_access_token(subject: str, tenant_id: str, *, version: int = 0) -> str:
    s = get_settings()
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": subject,
        "tenant": tenant_id,
        "ver": version,
        "iss": _TOKEN_ISSUER,
        "aud": _TOKEN_AUDIENCE,
        "iat": now,
        "exp": now + dt.timedelta(minutes=s.access_token_ttl_min),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_access_token_claims(
    token: str, *, tenant_id: str | None = None
) -> dict[str, Any] | None:
    """Decode a login token, rejecting purpose tokens and cross-tenant use."""
    s = get_settings()
    try:
        payload = jwt.decode(
            token,
            s.jwt_secret,
            algorithms=[s.jwt_algorithm],
            issuer=_TOKEN_ISSUER,
            audience=_TOKEN_AUDIENCE,
            options={"require": ["sub", "tenant", "ver", "iat", "exp", "iss", "aud"]},
        )
    except jwt.PyJWTError:
        return None
    # Login tokens carry no `purpose`; reject purpose-scoped tokens (reset/verify) here.
    if payload.get("purpose"):
        return None
    if tenant_id is not None and payload.get("tenant") != tenant_id:
        return None
    if not isinstance(payload.get("sub"), str) or not isinstance(payload.get("ver"), int):
        return None
    return payload


def decode_token(token: str, *, tenant_id: str | None = None) -> str | None:
    """Return the subject (user id) if the access token is valid, else None."""
    payload = decode_access_token_claims(token, tenant_id=tenant_id)
    return payload.get("sub") if payload else None


def create_purpose_token(
    subject: str,
    purpose: str,
    ttl_min: int,
    *,
    tenant_id: str,
    version: int | None = None,
    email: str | None = None,
) -> str:
    """Short-lived, single-purpose token (e.g. 'reset', 'verify') — separate from login tokens."""
    s = get_settings()
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": subject,
        "purpose": purpose,
        "tenant": tenant_id,
        "iss": _TOKEN_ISSUER,
        "aud": _TOKEN_AUDIENCE,
        "iat": now,
        "exp": now + dt.timedelta(minutes=ttl_min),
    }
    if version is not None:
        payload["ver"] = version
    if email is not None:
        payload["email"] = email
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_purpose_token_claims(
    token: str, purpose: str, *, tenant_id: str | None = None
) -> dict[str, Any] | None:
    """Decode purpose-scoped claims and optionally bind them to a tenant."""
    s = get_settings()
    try:
        payload = jwt.decode(
            token,
            s.jwt_secret,
            algorithms=[s.jwt_algorithm],
            issuer=_TOKEN_ISSUER,
            audience=_TOKEN_AUDIENCE,
            options={"require": ["sub", "purpose", "tenant", "iat", "exp", "iss", "aud"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != purpose:
        return None
    if tenant_id is not None and payload.get("tenant") != tenant_id:
        return None
    return payload


def decode_purpose_token(
    token: str, purpose: str, *, tenant_id: str | None = None
) -> str | None:
    claims = decode_purpose_token_claims(token, purpose, tenant_id=tenant_id)
    return claims.get("sub") if claims else None
