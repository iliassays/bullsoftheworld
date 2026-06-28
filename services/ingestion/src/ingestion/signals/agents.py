"""Agent system accounts — one user per beat, handle `bullsofdhaka-<beat>-agent`.

Idempotently seeded; notes are authored by these users so the feed can badge them as auto data
notes. Names are descriptive and stable so retail learns who posts what.
"""

from __future__ import annotations

from sqlalchemy import select

from bulls.core.models import User
from bulls.core.security import hash_password

# beat key -> (handle, display name). Phase 1 uses 'levels'; the rest seed ahead for later phases.
AGENTS: dict[str, tuple[str, str]] = {
    "levels": ("bullsofdhaka-levels-agent", "Price Levels"),
    "volume": ("bullsofdhaka-volume-agent", "Unusual Volume"),
    "foreign": ("bullsofdhaka-foreign-agent", "Foreign Flow"),
    "institution": ("bullsofdhaka-institution-agent", "Institutional Flow"),
    "sponsor": ("bullsofdhaka-sponsor-agent", "Insider / Sponsor"),
    "dividend": ("bullsofdhaka-dividend-agent", "Dividend"),
    "earnings": ("bullsofdhaka-earnings-agent", "Earnings"),
    "rating": ("bullsofdhaka-rating-agent", "Credit Rating"),
    "market": ("bullsofdhaka-market-update-agent", "Market Update"),
    # Factor beats — descriptive notes from the institutional-grade analytics
    "momentum": ("bullsofdhaka-momentum-agent", "Momentum"),
    "strength": ("bullsofdhaka-strength-agent", "Relative Strength"),
    "quality": ("bullsofdhaka-quality-agent", "Quality & Value"),
    "smartmoney": ("bullsofdhaka-smartmoney-agent", "Smart Money"),
    "accumulation": ("bullsofdhaka-accumulation-agent", "Accumulation"),
    "circuit": ("bullsofdhaka-circuit-agent", "Circuit Limit"),
    "breakout": ("bullsofdhaka-breakout-agent", "52-Week Breakout"),
}

# Agents never log in; an unusable hash keeps the account password-locked.
_LOCKED = hash_password("agent-no-login-" + "x" * 16)


async def ensure_agents(session, tenant_id: str) -> dict[str, int]:
    """Create any missing agent accounts; return {beat: user_id}."""
    existing = {
        u.handle: u
        for u in await session.scalars(
            select(User).where(User.handle.in_([h for h, _ in AGENTS.values()]))
        )
    }
    ids: dict[str, int] = {}
    for beat, (handle, name) in AGENTS.items():
        user = existing.get(handle)
        if user is None:
            user = User(
                tenant_id=tenant_id, handle=handle, name=name, password_hash=_LOCKED, locale="bn"
            )
            session.add(user)
            await session.flush()
        ids[beat] = user.id
    return ids
