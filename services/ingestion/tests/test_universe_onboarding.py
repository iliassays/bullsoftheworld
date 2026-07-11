from __future__ import annotations

from types import SimpleNamespace

import pytest

from ingestion import universe_onboarding


def test_promotion_is_fail_closed_when_feature_flag_is_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        universe_onboarding,
        "get_settings",
        lambda: SimpleNamespace(
            us_universe_promotion_enabled=False,
            us_market_data_authorization_id="contract-123",
        ),
    )

    with pytest.raises(ValueError, match="US_UNIVERSE_PROMOTION_ENABLED"):
        universe_onboarding._validate_promotion(True)


def test_promotion_requires_auditable_market_data_authorization(monkeypatch) -> None:
    monkeypatch.setattr(
        universe_onboarding,
        "get_settings",
        lambda: SimpleNamespace(
            us_universe_promotion_enabled=True,
            us_market_data_authorization_id="  ",
        ),
    )

    with pytest.raises(ValueError, match="US_MARKET_DATA_AUTHORIZATION_ID"):
        universe_onboarding._validate_promotion(True)


def test_promotion_is_allowed_only_when_both_controls_are_present(monkeypatch) -> None:
    monkeypatch.setattr(
        universe_onboarding,
        "get_settings",
        lambda: SimpleNamespace(
            us_universe_promotion_enabled=True,
            us_market_data_authorization_id="contract-123",
        ),
    )

    universe_onboarding._validate_promotion(True)


def test_staging_does_not_require_market_data_authorization(monkeypatch) -> None:
    monkeypatch.setattr(
        universe_onboarding,
        "get_settings",
        lambda: (_ for _ in ()).throw(AssertionError("settings should not be read")),
    )

    universe_onboarding._validate_promotion(False)
