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
    """Normalize a phone to E.164-ish (+<digits>). Lenient so both work:

    - Bangladeshi users without a country code: 01712345678 / 1712345678 → +8801712345678
    - International users with a country code: +14155552671, 14155552671 → +14155552671

    Returns None for anything too short/long to be a real number.
    """
    raw = s.strip()
    d = re.sub(r"\D", "", raw)
    if len(d) < 7:
        return None
    if raw.startswith("+"):
        return f"+{d}" if 8 <= len(d) <= 15 else None
    # Bangladesh conveniences (no country code typed):
    if d.startswith("0") and len(d) == 11 and d[1] == "1":  # 01XXXXXXXXX
        return f"+880{d[1:]}"
    if len(d) == 10 and d.startswith("1"):  # 1XXXXXXXXX (BD mobile minus the leading 0)
        return f"+880{d}"
    if d.startswith("880") and len(d) == 13:  # 8801XXXXXXXXX
        return f"+{d}"
    # Otherwise assume it already includes a country code (international).
    return f"+{d}" if 8 <= len(d) <= 15 else None


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
