from __future__ import annotations

from api.institutional_research.squeeze import LIMITATIONS, _blocked_families


def test_us_blocked_families_are_explicit_with_missing_datasets() -> None:
    blocked = {family.family: family for family in _blocked_families("US")}

    assert set(blocked) == {
        "us_short_squeeze",
        "us_gamma_squeeze",
        "us_float_liquidity_squeeze",
    }
    for family in blocked.values():
        assert family.blocked_reason
        assert family.missing_datasets
        assert family.entries == []

    # Gamma and float squeezes are still missing their core datasets outright.
    assert blocked["us_gamma_squeeze"].status == "data_blocked"
    assert blocked["us_float_liquidity_squeeze"].status == "data_blocked"
    # Short squeeze now HAS authoritative positioning (FINRA consolidated short interest), so
    # reporting it as data-blocked would misstate the reason: what it lacks is an evaluator,
    # plus float/borrow/FTD for full confidence. Execution stays blocked either way.
    assert blocked["us_short_squeeze"].status == "not_implemented"
    assert not any(
        "short interest" in item.lower() and "days-to-cover" in item.lower()
        for item in blocked["us_short_squeeze"].missing_datasets
    )


def test_dse_has_no_short_squeeze_family_at_all() -> None:
    assert _blocked_families("DSE") == []


def test_limitations_enforce_the_language_rules() -> None:
    blob = " ".join(LIMITATIONS).lower()
    assert "not short interest" in blob
    assert "days-to-cover" in blob
    assert "never live flow" in blob
    assert "nothing here is a prediction" in blob
    assert "not a price forecast" in blob
