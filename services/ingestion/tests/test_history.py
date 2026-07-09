from __future__ import annotations

from ingestion.history import _default_days, _mode_market, _select_codes


def test_mode_market_keeps_legacy_dse_cli_shape() -> None:
    assert _mode_market("backfill", None) == ("DSE", "backfill")
    assert _mode_market("daily", "US") == ("US", "daily")
    assert _mode_market("US", "backfill") == ("US", "backfill")


def test_us_backfill_defaults_to_ten_year_window() -> None:
    assert 3650 <= _default_days("US", "backfill") <= 3654
    assert _default_days("US", "daily") == 14


def test_select_codes_filters_then_slices_stably() -> None:
    codes = ["AAPL", "BRK.B", "MSFT", "NVDA", "TSLA"]
    assert _select_codes(codes, offset=1, limit=2) == ["BRK.B", "MSFT"]
    assert _select_codes(codes, wanted=["tsla", "aapl"], limit=5) == ["AAPL", "TSLA"]
