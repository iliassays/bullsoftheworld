from bulls.analytics.disclosure_materiality import (
    dse_disclosure_role,
    is_material_dse_disclosure,
)


def test_decoded_outcomes_are_material_but_empty_category_matches_are_not() -> None:
    assert is_material_dse_disclosure("earnings", {"eps_current": 2.4})
    assert is_material_dse_disclosure("dividend", {"no_dividend": True})
    assert is_material_dse_disclosure("rating", {"long_term": "AA"})

    assert not is_material_dse_disclosure("earnings", {"period": "Q3"})
    assert not is_material_dse_disclosure("dividend", {"agm_date": "2026-08-01"})
    assert not is_material_dse_disclosure("rating", None)


def test_calendar_notices_are_catalysts_without_becoming_research_outcomes() -> None:
    assert (
        dse_disclosure_role(
            "board_meeting",
            {"meeting_date": "2026-08-01", "agenda": ["financials"]},
        )
        == "catalyst"
    )
    assert (
        dse_disclosure_role(
            "corporate_action",
            {"record_date": "2026-08-05"},
        )
        == "catalyst"
    )


def test_structural_market_events_remain_material_without_a_decoder() -> None:
    assert dse_disclosure_role("halt", None) == "material"
    assert dse_disclosure_role("insider", None) == "material"
    assert dse_disclosure_role("psi", None) == "material"
    assert dse_disclosure_role("other", {"message": "administrative"}) == "routine"
