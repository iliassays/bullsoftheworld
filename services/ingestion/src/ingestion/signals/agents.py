"""Agent system accounts — one user per beat, handle `bullsofdhaka-<beat>-agent`.

Idempotently seeded; notes are authored by these users so the feed can badge them as auto data
notes. Names are descriptive and stable so retail learns who posts what.
"""

from __future__ import annotations

from sqlalchemy import select

from bulls.core.models import User
from bulls.core.security import hash_password

# beat key -> (handle, display name). Handles follow the StockTwits convention (@BullsOfDhaka<Topic>);
# migration b3c4d5e6f7a8's successor renamed the seeded rows to match. Display names stay descriptive.
AGENTS: dict[str, tuple[str, str]] = {
    "levels": ("BullsOfDhakaLevels", "Price Levels"),
    "volume": ("BullsOfDhakaVolume", "Unusual Volume"),
    "foreign": ("BullsOfDhakaForeign", "Foreign Flow"),
    "institution": ("BullsOfDhakaInstitution", "Institutional Flow"),
    "sponsor": ("BullsOfDhakaSponsor", "Insider / Sponsor"),
    "dividend": ("BullsOfDhakaDividend", "Dividend"),
    "earnings": ("BullsOfDhakaEarnings", "Earnings"),
    "rating": ("BullsOfDhakaRating", "Credit Rating"),
    "market": ("BullsOfDhakaMarket", "Market Update"),
    # Factor beats — descriptive notes from the institutional-grade analytics
    "momentum": ("BullsOfDhakaMomentum", "Momentum"),
    "strength": ("BullsOfDhakaStrength", "Relative Strength"),
    "quality": ("BullsOfDhakaQuality", "Quality & Value"),
    "smartmoney": ("BullsOfDhakaSmartMoney", "Smart Money"),
    "accumulation": ("BullsOfDhakaAccumulation", "Accumulation"),
    "circuit": ("BullsOfDhakaCircuit", "Circuit Limit"),
    "breakout": ("BullsOfDhakaBreakout", "52-Week Breakout"),
}

# Agents never log in; an unusable hash keeps the account password-locked.
_LOCKED = hash_password("agent-no-login-" + "x" * 16)


async def ensure_agents(session, tenant_id: str) -> dict[str, int]:
    """Create any missing agent accounts; return {beat: user_id}."""
    existing = {
        u.handle: u
        for u in await session.scalars(
            select(User).where(
                User.tenant_id == tenant_id,
                User.handle.in_([h for h, _ in AGENTS.values()]),
            )
        )
    }
    ids: dict[str, int] = {}
    for beat, (handle, name) in AGENTS.items():
        user = existing.get(handle)
        if user is None:
            user = User(
                tenant_id=tenant_id,
                handle=handle,
                name=name,
                password_hash=_LOCKED,
                locale="bn",
                is_official=True,
            )
            session.add(user)
            await session.flush()
        elif not user.is_official:  # backfill for accounts seeded before the flag existed
            user.is_official = True
        ids[beat] = user.id
    return ids
