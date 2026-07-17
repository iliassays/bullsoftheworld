from __future__ import annotations

import datetime as dt

from sqlalchemy.dialects import postgresql

from ingestion.analytics import _LOOKBACK, _bar_batch_statement, analytics_cutoff_date


def test_bar_batch_query_uses_bounded_lateral_index_lookups() -> None:
    sql = str(
        _bar_batch_statement(
            "US",
            ["AAPL", "MSFT"],
            through_date=dt.date(2026, 7, 16),
        ).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "join lateral" in sql
    assert "requested_codes" in sql
    assert "daily_bars.market = 'us'" in sql
    assert "daily_bars.date <= '2026-07-16'" in sql
    assert f"limit {_LOOKBACK}" in sql
    assert "row_number" not in sql


def test_analytics_cutoff_excludes_an_open_us_session() -> None:
    assert analytics_cutoff_date(
        "US",
        now=dt.datetime(2026, 7, 17, 14, 0, tzinfo=dt.UTC),
    ) == dt.date(2026, 7, 16)
