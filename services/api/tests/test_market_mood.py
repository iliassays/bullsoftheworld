"""Pure freshness rules for the quote-aware market mood card."""

from __future__ import annotations

import datetime as dt

from api.routers.market import _mood_data_status


def _utc(hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(2026, 7, 14, hour, minute, tzinfo=dt.UTC)


def test_current_quote_batch_is_intraday_during_dse_session() -> None:
    assert _mood_data_status(_utc(4, 30), "DSE", _utc(4, 15), dt.date(2026, 7, 13)) == (
        "intraday_delayed"
    )


def test_late_quote_batch_is_exposed_as_stale() -> None:
    assert _mood_data_status(_utc(4, 30), "DSE", _utc(3, 45), dt.date(2026, 7, 13)) == ("stale")


def test_final_delayed_batch_is_provisional_until_eod_lands() -> None:
    assert _mood_data_status(_utc(9), "DSE", _utc(8, 45), dt.date(2026, 7, 13)) == (
        "provisional_close"
    )


def test_incomplete_post_close_batch_is_not_called_provisional_close() -> None:
    assert _mood_data_status(_utc(9), "DSE", _utc(7, 30), dt.date(2026, 7, 13)) == "stale"


def test_completed_eod_row_is_official_close() -> None:
    assert _mood_data_status(_utc(9), "DSE", _utc(8, 45), dt.date(2026, 7, 14)) == (
        "official_close"
    )
