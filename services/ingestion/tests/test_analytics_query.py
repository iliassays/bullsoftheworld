from __future__ import annotations

from sqlalchemy.dialects import postgresql

from ingestion.analytics import _LOOKBACK, _bar_batch_statement


def test_bar_batch_query_uses_bounded_lateral_index_lookups() -> None:
    sql = str(
        _bar_batch_statement("US", ["AAPL", "MSFT"]).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "join lateral" in sql
    assert "requested_codes" in sql
    assert "daily_bars.market = 'us'" in sql
    assert f"limit {_LOOKBACK}" in sql
    assert "row_number" not in sql
