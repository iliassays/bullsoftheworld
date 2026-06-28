"""Identity helpers for the simple (Bangladesh-friendly) signup/login.

Signup takes name + (email OR phone) + password; the handle is generated from the name. Login
accepts email, phone, or that auto-handle. Phones are normalized to +8801XXXXXXXXX.
"""

from __future__ import annotations

import re

from sqlalchemy import func, select

from bulls.core.models import User

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_email(s: str) -> bool:
    return bool(_EMAIL_RE.match(s.strip()))


def normalize_phone(s: str) -> str | None:
    """BD mobile → +8801XXXXXXXXX. None if it isn't a plausible BD mobile number."""
    d = re.sub(r"\D", "", s)
    if d.startswith("00"):
        d = d[2:]
    if d.startswith("880"):
        d = d[3:]
    elif d.startswith("0"):
        d = d[1:]
    # BD mobile local part = 10 digits starting with 1 (e.g. 1712345678)
    return f"+880{d}" if len(d) == 10 and d.startswith("1") else None


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


async def generate_handle(session, name: str, email: str | None, phone: str | None) -> str:
    """Unique, URL-safe handle from the name; falls back to email/phone (e.g. for Bangla names)."""
    base = _slug(name)[:14]
    if len(base) < 3 and email:
        base = _slug(email.split("@")[0])[:14]
    if len(base) < 3 and phone:
        base = "u" + phone[-6:]
    if len(base) < 3:
        base = "bull"
    handle, n = base, 1
    while await session.scalar(select(User.id).where(func.lower(User.handle) == handle)):
        n += 1
        handle = f"{base}{n}"
    return handle
