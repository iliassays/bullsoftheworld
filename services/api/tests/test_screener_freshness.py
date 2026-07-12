from api.routers.screener import _screenable_codes


def test_market_screen_universe_is_pinned_to_latest_analytics_date() -> None:
    sql = str(_screenable_codes("DSE")).lower()
    assert "max(" in sql
    assert "as_of_date" in sql
