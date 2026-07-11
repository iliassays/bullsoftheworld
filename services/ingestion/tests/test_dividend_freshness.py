from ingestion.analytics import _is_current_dividend_year


def test_current_or_prior_reporting_year_can_feed_current_yield() -> None:
    assert _is_current_dividend_year(2026, 2026)
    assert _is_current_dividend_year(2025, 2026)


def test_old_or_future_dividend_cannot_feed_current_yield() -> None:
    assert not _is_current_dividend_year(2021, 2026)
    assert not _is_current_dividend_year(2027, 2026)
