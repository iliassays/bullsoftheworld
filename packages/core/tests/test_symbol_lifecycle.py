from bulls.core.models import Symbol
from bulls.core.symbol_lifecycle import research_publication_status


def _symbol(status: str, *, hidden: bool = False) -> Symbol:
    return Symbol(
        market="US",
        code="TEST",
        name_en="Test Inc.",
        is_active=True,
        is_hidden=hidden,
        data_status=status,
    )


def test_public_research_is_explicit_and_does_not_include_degraded_data() -> None:
    assert _symbol("ready").is_public_research
    assert _symbol("research_only").is_public_research
    assert not _symbol("degraded").is_public_research
    assert not _symbol("research_only", hidden=True).is_public_research


def test_research_publication_keeps_critical_data_failures_private() -> None:
    assert research_publication_status(True, []) == "ready"
    assert research_publication_status(False, ["nonzero_volume"]) == "research_only"
    assert (
        research_publication_status(
            False,
            ["product_eligible", "nonzero_volume"],
        )
        == "research_only"
    )
    assert research_publication_status(False, ["sec_filings"]) is None
    assert research_publication_status(False, ["freshness", "liquidity"]) is None
