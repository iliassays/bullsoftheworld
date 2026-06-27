"""Auth helpers: password hashing + JWT."""

from __future__ import annotations

import datetime as dt

import bcrypt
import jwt

from bulls.core.config import get_settings


def _to_bytes(password: str) -> bytes:
    # bcrypt only considers the first 72 bytes; truncate explicitly so longer
    # passwords don't raise on bcrypt >= 4.1.
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(_to_bytes(password), hashed.encode("utf-8"))


def create_access_token(subject: str) -> str:
    s = get_settings()
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + dt.timedelta(minutes=s.access_token_ttl_min),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_token(token: str) -> str | None:
    """Return the subject (user id) if the token is valid, else None."""
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    # Login tokens carry no `purpose`; reject purpose-scoped tokens (reset/verify) here.
    if payload.get("purpose"):
        return None
    return payload.get("sub")


def create_purpose_token(subject: str, purpose: str, ttl_min: int) -> str:
    """Short-lived, single-purpose token (e.g. 'reset', 'verify') — separate from login tokens."""
    s = get_settings()
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": subject,
        "purpose": purpose,
        "iat": now,
        "exp": now + dt.timedelta(minutes=ttl_min),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_purpose_token(token: str, purpose: str) -> str | None:
    """Return the subject if the token is valid AND was minted for `purpose`, else None."""
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != purpose:
        return None
    return payload.get("sub")
