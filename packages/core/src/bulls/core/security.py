"""Auth helpers: password hashing + JWT. Stubs to flesh out in step 3."""

from __future__ import annotations

import datetime as dt

import jwt
from passlib.context import CryptContext

from bulls.core.config import get_settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _pwd.verify(password, hashed)


def create_access_token(subject: str) -> str:
    s = get_settings()
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + dt.timedelta(minutes=s.access_token_ttl_min),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)
