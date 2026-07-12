"""Privacy-preserving identifiers shared by first-party analytics endpoints."""

from __future__ import annotations

import hashlib
import hmac

from bulls.core.config import get_settings


def anonymous_session_hash(tenant_id: str, session_id: str | None) -> str | None:
    if not session_id:
        return None
    return hmac.new(
        get_settings().jwt_secret.encode(),
        f"{tenant_id}:{session_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
