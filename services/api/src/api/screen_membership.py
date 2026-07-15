"""Ephemeral, tenant-isolated membership state for market discovery boards.

This is presentation freshness, not an investment signal or permanent audit record. Redis is the
right boundary: membership changes with ranking refreshes, while the underlying source facts remain
in Postgres. The first observed board is always a baseline so the API never invents retroactive
"new" claims.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence
from typing import Protocol

from redis.asyncio import Redis

_SCREEN_MEMBERSHIP_TTL = 90 * 24 * 60 * 60
_NEW_TO_SCREEN_WINDOW = dt.timedelta(hours=24)
_SCREEN_MEMBERSHIP_VERSION = 1


class MembershipItem(Protocol):
    code: str
    new_since: str | None


class MembershipBoard(Protocol):
    key: str
    items: list[MembershipItem]


def screen_membership_key(tenant_name: str, market: str, cap_tier: str | None) -> str:
    """Stable state key; tenant, market and selected universe are separate dimensions."""

    return f"screen-membership:v1:{tenant_name}:{market}:{cap_tier or 'all'}"


def _recent_entry(value: object, now: dt.datetime) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        entered_at = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if entered_at.tzinfo is None:
        entered_at = entered_at.replace(tzinfo=dt.UTC)
    age = now - entered_at.astimezone(dt.UTC)
    return value if dt.timedelta(0) <= age <= _NEW_TO_SCREEN_WINDOW else None


def apply_screen_membership_badges(
    boards: Sequence[MembershipBoard], state: dict[str, object] | None, now: dt.datetime
) -> None:
    """Apply recent-entry timestamps from an already-established membership baseline."""

    stored_screens = state.get("screens") if isinstance(state, dict) else None
    if not isinstance(stored_screens, dict):
        return
    for board in boards:
        stored_members = stored_screens.get(board.key)
        if not isinstance(stored_members, dict):
            continue
        for item in board.items:
            item.new_since = _recent_entry(stored_members.get(item.code), now)


def advance_screen_memberships(
    boards: Sequence[MembershipBoard], previous: dict[str, object] | None, now: dt.datetime
) -> dict[str, object]:
    """Advance continuous membership and mark only genuine entries after the baseline.

    Leaving removes a code from current state, so a later re-entry receives a fresh timestamp.
    """

    previous_screens = (
        previous.get("screens")
        if isinstance(previous, dict) and previous.get("version") == _SCREEN_MEMBERSHIP_VERSION
        else None
    )
    if not isinstance(previous_screens, dict):
        previous_screens = {}
    now_iso = now.astimezone(dt.UTC).isoformat()
    next_screens: dict[str, dict[str, str | None]] = {}

    for board in boards:
        previous_members = previous_screens.get(board.key)
        has_baseline = isinstance(previous_members, dict)
        if not has_baseline:
            previous_members = {}
        current_members: dict[str, str | None] = {}
        for item in board.items:
            if item.code in previous_members:
                entered_at = previous_members[item.code]
                entered_at = entered_at if isinstance(entered_at, str) else None
            else:
                entered_at = now_iso if has_baseline else None
            current_members[item.code] = entered_at
        next_screens[board.key] = current_members

    state: dict[str, object] = {
        "version": _SCREEN_MEMBERSHIP_VERSION,
        "generated_at": now_iso,
        "screens": next_screens,
    }
    apply_screen_membership_badges(boards, state, now)
    return state


def _decode_membership_state(raw: bytes | str | None) -> dict[str, object] | None:
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return None
    return value if isinstance(value, dict) else None


async def update_screen_memberships(
    redis: Redis,
    key: str,
    boards: Sequence[MembershipBoard],
    *,
    now: dt.datetime | None = None,
) -> None:
    observed_at = now or dt.datetime.now(dt.UTC)
    previous = _decode_membership_state(await redis.get(key))
    state = advance_screen_memberships(boards, previous, observed_at)
    await redis.set(
        key,
        json.dumps(state, separators=(",", ":")),
        ex=_SCREEN_MEMBERSHIP_TTL,
    )


async def apply_stored_screen_memberships(
    redis: Redis,
    key: str,
    boards: Sequence[MembershipBoard],
    *,
    now: dt.datetime | None = None,
) -> None:
    state = _decode_membership_state(await redis.get(key))
    apply_screen_membership_badges(boards, state, now or dt.datetime.now(dt.UTC))
