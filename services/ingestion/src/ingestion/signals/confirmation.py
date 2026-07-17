"""Short-lived confirmation state for provisional intraday observations.

The durable signal ledger records published events. This module handles the earlier question:
whether the same provisional state survived more than one distinct delayed quote snapshot. Redis
is appropriate because confirmation state is disposable and must never become research evidence.
"""

from __future__ import annotations

import json
from typing import Protocol


class SignalConfirmationStore(Protocol):
    async def get(self, name: str) -> str | bytes | None: ...

    async def set(self, name: str, value: str, *, ex: int) -> object: ...


async def state_is_confirmed(
    store: SignalConfirmationStore,
    *,
    key: str,
    observed_at: str,
    state: str,
    required_observations: int = 2,
    ttl_seconds: int = 2 * 24 * 60 * 60,
) -> bool:
    """Return true after ``state`` persists across distinct observations.

    Reprocessing the same quote timestamp never increments the count. A direction/state change
    starts confirmation over, which prevents a buying observation followed by selling pressure
    from being presented as one persistent signal.
    """

    if required_observations < 1:
        raise ValueError("required_observations must be positive")
    if required_observations == 1:
        return True

    count = 1
    raw = await store.get(key)
    if raw is not None:
        try:
            decoded = raw.decode() if isinstance(raw, bytes) else raw
            previous = json.loads(decoded)
            if previous.get("observed_at") == observed_at:
                return int(previous.get("count", 1)) >= required_observations
            if previous.get("state") == state:
                count = int(previous.get("count", 1)) + 1
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            count = 1

    await store.set(
        key,
        json.dumps({"count": count, "observed_at": observed_at, "state": state}),
        ex=ttl_seconds,
    )
    return count >= required_observations
