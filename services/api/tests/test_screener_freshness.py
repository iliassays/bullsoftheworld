from api.routers.screener import (
    _screenable_analytics_date_query,
    _screenable_analytics_timestamp_query,
    _screenable_codes,
)


def test_market_screen_universe_is_pinned_to_latest_analytics_date() -> None:
    sql = str(_screenable_codes("DSE")).lower()
    assert "max(" in sql
    assert "as_of_date" in sql
    assert "symbols.data_status" in sql
    assert "symbols.is_active" in sql
    assert "symbols.is_hidden" in sql


def test_public_cutoff_excludes_non_ready_analytics_rows() -> None:
    sql = str(_screenable_analytics_date_query("US")).lower()
    assert "join ticker_analytics" in sql
    assert "symbols.data_status" in sql
    assert "symbols.is_active" in sql
    assert "symbols.is_hidden" in sql


def test_public_freshness_timestamp_is_pinned_to_public_cutoff() -> None:
    sql = str(_screenable_analytics_timestamp_query("US")).lower()
    assert "max(" in sql
    assert "computed_at" in sql
    assert "as_of_date" in sql
    assert "symbols.data_status" in sql
