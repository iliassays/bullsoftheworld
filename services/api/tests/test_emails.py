from __future__ import annotations

from pathlib import Path

from api.emails import verify_welcome
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
