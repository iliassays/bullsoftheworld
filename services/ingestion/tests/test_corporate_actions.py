import datetime as dt
from types import SimpleNamespace

import pytest

from ingestion.corporate_actions import (
    theoretical_adjustment_factor,
    verified_action_candidates,
)


def _announcement(
    row_id: int,
    *,
    code: str,
    published_at: dt.date,
    headline: str,
    body: str,
    category: str = "corporate_action",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=row_id,
        code=code,
        published_at=published_at,
        category=category,
        headline=headline,
        body=body,
        details=None,
        created_at=dt.datetime.combine(published_at, dt.time(12), tzinfo=dt.UTC),
    )


def test_verified_candidates_require_complete_bonus_terms() -> None:
    complete = _announcement(
        1,
        code="BONUS",
        published_at=dt.date(2026, 5, 1),
        category="dividend",
        headline="Dividend Declaration",
        body="10% Stock Dividend. Record Date: 20.05.2026.",
    )
    incomplete = _announcement(
        2,
        code="MISSING",
        published_at=dt.date(2026, 5, 1),
        category="dividend",
        headline="Dividend Declaration",
        body="5% Stock Dividend. Record date will be notified later.",
    )

    candidates, diagnostics = verified_action_candidates([complete, incomplete])

    assert len(candidates) == 1
    assert candidates[0].action_type == "bonus"
    assert candidates[0].bonus_ratio == pytest.approx(0.10)
    assert candidates[0].record_date == dt.date(2026, 5, 20)
    assert diagnostics["incomplete_bonus"] == 1


def test_verified_candidates_link_rights_terms_to_later_record_notice() -> None:
    terms = _announcement(
        10,
        code="RIGHTS",
        published_at=dt.date(2025, 5, 28),
        headline="BSEC consent for issuance of Rights Share",
        body=(
            "Issuance of 1:17 Rights Share (1 Rights Share against 17 existing shares) "
            "at an issue price of BDT 1,110 per share."
        ),
    )
    record = _announcement(
        11,
        code="RIGHTS",
        published_at=dt.date(2025, 5, 29),
        headline="Record Date for Rights Share Issuance",
        body="Record Date for Determination of Entitlement of Rights Share: June 29, 2025.",
    )

    candidates, diagnostics = verified_action_candidates([terms, record])

    assert diagnostics["incomplete_rights"] == 0
    assert len(candidates) == 1
    assert candidates[0].action_type == "rights"
    assert candidates[0].rights_ratio == pytest.approx(1 / 17)
    assert candidates[0].rights_subscription_price == 1110.0
    assert candidates[0].source_announcement_ids == (10, 11)


def test_rights_record_without_verified_terms_is_omitted() -> None:
    record = _announcement(
        20,
        code="RIGHTS",
        published_at=dt.date(2025, 5, 29),
        headline="Record Date for Rights Share Issuance",
        body="Record Date for Entitlement of Rights Share: June 29, 2025.",
    )

    candidates, diagnostics = verified_action_candidates([record])

    assert candidates == []
    assert diagnostics["incomplete_rights"] == 1


def test_adjustment_factor_supports_bonus_rights_and_large_bonus() -> None:
    assert theoretical_adjustment_factor(
        reference_close=120.0,
        bonus_ratio=5.0,
    ) == pytest.approx(1 / 6)
    assert theoretical_adjustment_factor(
        reference_close=100.0,
        bonus_ratio=0.10,
        rights_ratio=0.20,
        rights_subscription_price=50.0,
    ) == pytest.approx((100 + 0.2 * 50) / (100 * 1.3))
