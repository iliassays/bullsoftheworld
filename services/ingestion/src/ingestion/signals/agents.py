"""Agent system accounts — one user per beat, handle `bullsofdhaka-<beat>-agent`.

Idempotently seeded; notes are authored by these users so the feed can badge them as auto data
notes. Names are descriptive and stable so retail learns who posts what.
"""

from __future__ import annotations

from sqlalchemy import select

from bulls.core.db import bind_tenant_context
from bulls.core.models import User
from bulls.core.security import hash_password

_AGENT_DEFS: dict[str, tuple[str, str]] = {
    "levels": ("Levels", "Price Levels"),
    "volume": ("Volume", "Unusual Volume"),
    "foreign": ("Foreign", "Foreign Flow"),
    "institution": ("Institution", "Institutional Flow"),
    "sponsor": ("Sponsor", "Insider / Sponsor"),
    "dividend": ("Dividend", "Dividend"),
    "earnings": ("Earnings", "Earnings"),
    "rating": ("Rating", "Credit Rating"),
    "market": ("Market", "Market Update"),
    # Factor beats — descriptive notes from the institutional-grade analytics
    "momentum": ("Momentum", "Momentum"),
    "strength": ("Strength", "Relative Strength"),
    "quality": ("Quality", "Quality & Value"),
    "smartmoney": ("SmartMoney", "Smart Money"),
    "accumulation": ("Accumulation", "Accumulation"),
    "circuit": ("Circuit", "Circuit Limit"),
    "breakout": ("Breakout", "52-Week Breakout"),
    "shorts": ("Shorts", "Short Volume"),  # US: FINRA Reg SHO daily short-sale share
    "filings": ("Filings", "SEC Filings"),
}

_TENANT_AGENT_BRANDS = {
    "bullsofdhaka": ("BullsOfDhaka", "bn"),
    "bullsofwallst": ("BullsOfWallSt", "en"),
}

_TENANT_BEATS: dict[str, frozenset[str]] = {
    "bullsofdhaka": frozenset(_AGENT_DEFS) - {"shorts", "filings"},
    "bullsofwallst": frozenset(
        {
            "levels",
            "volume",
            "institution",
            "earnings",
            "market",
            "momentum",
            "strength",
            "quality",
            "accumulation",
            "breakout",
            "shorts",
            "filings",
        }
    ),
}


def agent_identity(tenant_id: str, beat: str) -> tuple[str, str]:
    prefix, _ = _TENANT_AGENT_BRANDS[tenant_id]
    suffix, name = _AGENT_DEFS[beat]
    return f"{prefix}{suffix}", name


# DSE compatibility for existing imports and migrations. Runtime code resolves through
# agent_identity(), so a shared worker can never author Wall Street notes with a Dhaka handle.
AGENTS = {beat: agent_identity("bullsofdhaka", beat) for beat in _AGENT_DEFS}

# Agents never log in; an unusable hash keeps the account password-locked.
_LOCKED = hash_password("agent-no-login-" + "x" * 16)


async def ensure_agents(session, tenant_id: str) -> dict[str, int]:
    """Create any missing agent accounts; return {beat: user_id}."""
    await bind_tenant_context(session, tenant_id)
    supported = _TENANT_BEATS[tenant_id]
    all_identities = {beat: agent_identity(tenant_id, beat) for beat in _AGENT_DEFS}
    identities = {beat: all_identities[beat] for beat in sorted(supported)}
    existing = {
        u.handle: u
        for u in await session.scalars(
            select(User).where(
                User.tenant_id == tenant_id,
                User.handle.in_([handle for handle, _ in all_identities.values()]),
            )
        )
    }
    supported_handles = {handle for handle, _ in identities.values()}
    for handle, user in existing.items():
        if handle not in supported_handles and user.is_official:
            user.is_official = False
    ids: dict[str, int] = {}
    for beat, (handle, name) in identities.items():
        user = existing.get(handle)
        if user is None:
            _, locale = _TENANT_AGENT_BRANDS[tenant_id]
            user = User(
                tenant_id=tenant_id,
                handle=handle,
                name=name,
                password_hash=_LOCKED,
                locale=locale,
                is_official=True,
            )
            session.add(user)
            await session.flush()
        elif not user.is_official:  # backfill for accounts seeded before the flag existed
            user.is_official = True
        ids[beat] = user.id
    return ids
