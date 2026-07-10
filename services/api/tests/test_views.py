from __future__ import annotations

from api.routers.views import _anonymous_session_hash


def test_anonymous_page_view_id_is_hashed_and_tenant_bound() -> None:
    raw = "browser-session-123"
    dhaka = _anonymous_session_hash("bullsofdhaka", raw)
    wallst = _anonymous_session_hash("bullsofwallst", raw)

    assert dhaka is not None and len(dhaka) == 64
    assert raw not in dhaka
    assert wallst != dhaka
    assert _anonymous_session_hash("bullsofdhaka", None) is None
