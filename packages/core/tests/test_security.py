from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from bulls.core import security
from bulls.core.config import Settings
from bulls.core.security import (
    create_access_token,
    create_purpose_token,
    decode_access_token_claims,
    decode_purpose_token_claims,
    decode_token,
)


@pytest.fixture(autouse=True)
def secure_jwt_test_settings(monkeypatch) -> None:
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            jwt_secret="test-only-secret-key-with-32-bytes",
            jwt_algorithm="HS256",
            access_token_ttl_min=30,
        ),
    )


def test_access_token_is_bound_to_issuing_tenant() -> None:
    token = create_access_token("42", "bullsofdhaka", version=3)

    assert decode_token(token, tenant_id="bullsofdhaka") == "42"
    assert decode_token(token, tenant_id="bullsofwallst") is None
    assert decode_access_token_claims(token, tenant_id="bullsofdhaka")["ver"] == 3


def test_purpose_token_enforces_purpose_tenant_and_version() -> None:
    token = create_purpose_token(
        "42",
        "reset",
        30,
        tenant_id="bullsofwallst",
        version=7,
        email="trader@example.com",
    )

    claims = decode_purpose_token_claims(
        token, "reset", tenant_id="bullsofwallst"
    )
    assert claims is not None
    assert claims["sub"] == "42"
    assert claims["ver"] == 7
    assert claims["email"] == "trader@example.com"
    assert decode_purpose_token_claims(token, "verify", tenant_id="bullsofwallst") is None
    assert decode_purpose_token_claims(token, "reset", tenant_id="bullsofdhaka") is None
    assert decode_token(token, tenant_id="bullsofwallst") is None


def test_production_rejects_development_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, env="production", jwt_secret="change-me-in-prod")


def test_production_accepts_long_random_jwt_secret() -> None:
    settings = Settings(_env_file=None, env="production", jwt_secret="x" * 48)
    assert settings.env == "production"


def test_unknown_ai_provider_is_rejected_at_configuration_boundary() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ai_provider="mystery")
