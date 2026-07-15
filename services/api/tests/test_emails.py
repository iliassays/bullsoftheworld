from __future__ import annotations

from pathlib import Path

from api.emails import verify_welcome
from api.routers.auth import _link
from bulls.core.tenancy import TenantRegistry


def test_transactional_email_uses_tenant_brand_and_escapes_user_content() -> None:
    tenants_dir = Path(__file__).resolve().parents[3] / "tenants"
    tenant = TenantRegistry.from_dir(tenants_dir, default="bullsofdhaka").get("bullsofwallst")
    assert tenant is not None

    subject, html, text = verify_welcome(
        "<script>alert(1)</script>",
        "https://bullsofwallst.com/verify?token=a&b=c",
        "en",
        tenant,
    )

    assert subject.endswith("Bulls of Wall Street")
    assert "Bulls of Dhaka" not in html
    assert "bullsofdhaka.com" not in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "token=a&amp;b=c" in html
    assert "background:#2563EB" in html
    assert "Bulls of Wall Street" in text


def test_account_action_links_are_tenant_localized_and_query_encoded() -> None:
    tenants_dir = Path(__file__).resolve().parents[3] / "tenants"
    registry = TenantRegistry.from_dir(tenants_dir, default="bullsofdhaka")
    dhaka = registry.get("bullsofdhaka")
    wall_street = registry.get("bullsofwallst")
    assert dhaka is not None
    assert wall_street is not None

    assert _link(dhaka, "/reset", "a+b/c=", "bn") == (
        "https://bullsofdhaka.com/bn/reset?token=a%2Bb%2Fc%3D"
    )
    assert _link(dhaka, "/verify", "token", "en") == (
        "https://bullsofdhaka.com/en/verify?token=token"
    )
    assert _link(wall_street, "/reset", "token", "bn") == (
        "https://bullsofwallst.com/en/reset?token=token"
    )
