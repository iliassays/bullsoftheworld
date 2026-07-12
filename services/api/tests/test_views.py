from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.analytics_identity import anonymous_session_hash
from api.routers.views import ViewIn


def test_anonymous_page_view_id_is_hashed_and_tenant_bound() -> None:
    raw = "browser-session-123"
    dhaka = anonymous_session_hash("bullsofdhaka", raw)
    wallst = anonymous_session_hash("bullsofwallst", raw)

    assert dhaka is not None and len(dhaka) == 64
    assert raw not in dhaka
    assert wallst != dhaka
    assert anonymous_session_hash("bullsofdhaka", None) is None


def test_page_view_requires_analytics_consent() -> None:
    assert ViewIn(analytics_consent=True, session_id="browser-session-123").analytics_consent
    with pytest.raises(ValidationError):
        ViewIn(analytics_consent=False, session_id="browser-session-123")
