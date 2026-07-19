import pytest

from ingestion.news_decode import decode


def test_dividend_decode_includes_bonus_record_date() -> None:
    details = decode(
        "dividend",
        "PRAGATILIF: Dividend Declaration",
        (
            "The Board of Directors has recommended 15% Cash and 10% Stock dividend. "
            "Record Date: 14-Jul-2026."
        ),
    )

    assert details["stock_pct"] == 10.0
    assert details["record_date"] == "2026-07-14"


@pytest.mark.parametrize(
    ("body", "ratio", "price"),
    [
        (
            "Issuance of Right Shares: Rights Ratio- 2:1 "
            "(1 Right Share for every 2 existing shares) and Offer Price: BDT 10 per share.",
            0.5,
            10.0,
        ),
        (
            "Issuance of 1:17 Rights Share (1 Rights Share against 17 existing shares) "
            "at an issue price of BDT 1,110 per share.",
            1 / 17,
            1110.0,
        ),
    ],
)
def test_rights_decode_prefers_explicit_entitlement(
    body: str,
    ratio: float,
    price: float,
) -> None:
    details = decode("corporate_action", "Rights Share", body)

    assert details["rights_ratio"] == pytest.approx(ratio)
    assert details["rights_subscription_price"] == price


def test_corporate_action_decode_accepts_real_dse_record_date_shapes() -> None:
    details = decode(
        "corporate_action",
        "Record Date",
        "Record Date for Determination of Entitlement of Rights Share: June 29, 2025.",
    )

    assert details["record_date"] == "2025-06-29"


def test_record_date_decoder_does_not_borrow_an_unrelated_later_date() -> None:
    details = decode(
        "corporate_action",
        "Rights approval",
        (
            "The record date for entitlement will be notified later. "
            "The approval letter was dated September 12, 2021."
        ),
    )

    assert "record_date" not in details
