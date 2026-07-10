from bulls.core.models import SecFiling


def test_sec_filing_identity_preserves_each_ticker_for_shared_issuers() -> None:
    assert tuple(column.name for column in SecFiling.__table__.primary_key.columns) == (
        "market",
        "code",
        "accession_number",
    )
