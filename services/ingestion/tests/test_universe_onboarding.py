from __future__ import annotations

from types import SimpleNamespace

import pytest

from ingestion import universe_onboarding
from ingestion.cohorts import CohortManifest, OnboardingPolicy


def _manifest(*, requires_risk_review: bool = False, risk_review_id: str | None = None):
    return CohortManifest(
        name="test",
        market="US",
        symbols=("TEST",),
        policy=OnboardingPolicy(requires_risk_review=requires_risk_review),
        risk_review_id=risk_review_id,
        manifest_sha256="a" * 64,
    )


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
        universe_onboarding._validate_promotion(True, _manifest())


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
        universe_onboarding._validate_promotion(True, _manifest())


def test_promotion_is_allowed_only_when_both_controls_are_present(monkeypatch) -> None:
    monkeypatch.setattr(
        universe_onboarding,
        "get_settings",
        lambda: SimpleNamespace(
            us_universe_promotion_enabled=True,
            us_market_data_authorization_id="contract-123",
        ),
    )

    universe_onboarding._validate_promotion(True, _manifest())


def test_staging_does_not_require_market_data_authorization(monkeypatch) -> None:
    monkeypatch.setattr(
        universe_onboarding,
        "get_settings",
        lambda: (_ for _ in ()).throw(AssertionError("settings should not be read")),
    )

    universe_onboarding._validate_promotion(False, _manifest())


def test_owner_directed_research_publication_requires_a_named_acknowledgement() -> None:
    with pytest.raises(ValueError, match="risk_review_id"):
        universe_onboarding._validate_promotion(
            False,
            _manifest(),
            publish_research=True,
        )

    universe_onboarding._validate_promotion(
        False,
        _manifest(risk_review_id="owner-ack-2026-07"),
        publish_research=True,
    )


def test_publication_modes_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        universe_onboarding._validate_promotion(
            True,
            _manifest(risk_review_id="owner-ack-2026-07"),
            publish_research=True,
        )


def test_enhanced_risk_cohort_requires_named_review_before_promotion(monkeypatch) -> None:
    monkeypatch.setattr(
        universe_onboarding,
        "get_settings",
        lambda: (_ for _ in ()).throw(AssertionError("settings should not be read")),
    )

    with pytest.raises(ValueError, match="risk_review_id"):
        universe_onboarding._validate_promotion(
            True,
            _manifest(requires_risk_review=True),
        )


def test_named_risk_review_allows_normal_authorization_checks(monkeypatch) -> None:
    monkeypatch.setattr(
        universe_onboarding,
        "get_settings",
        lambda: SimpleNamespace(
            us_universe_promotion_enabled=True,
            us_market_data_authorization_id="contract-123",
        ),
    )

    universe_onboarding._validate_promotion(
        True,
        _manifest(requires_risk_review=True, risk_review_id="review-2026-001"),
    )
