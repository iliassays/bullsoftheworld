from __future__ import annotations

import csv
import datetime as dt
import io
import zipfile

import pytest

from bulls.market_data.options.cboe_sentiment import (
    CBOE_OPTION_SENTIMENT_COLUMNS,
    _number,
    parse_cboe_option_sentiment,
)


def _row(**updates: str) -> dict[str, str]:
    row = {field: "0" for field in CBOE_OPTION_SENTIMENT_COLUMNS}
    row.update(
        {
            "trade_date": "2026-07-15",
            "underlying_symbol": "AAPL",
            "call_volume": "70",
            "put_volume": "30",
            "total_volume": "100",
            "call_trades": "7",
            "put_trades": "3",
            "total_trades": "10",
            "spot_close": "210.5",
            "split_adj_close": "210.5",
            "underlying_security_type": "S",
            "directional_pct": "82.5",
        }
    )
    row.update(updates)
    return row


def _csv(*rows: dict[str, str]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CBOE_OPTION_SENTIMENT_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def _zip(payload: bytes) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("HighLevelOptionSentiment_Complete_2026-07-15.csv", payload)
    return output.getvalue()


def test_parser_preserves_blank_as_unavailable_and_accepts_complete_zip() -> None:
    parsed = parse_cboe_option_sentiment(
        _zip(_csv(_row(avg_call_size="", cust_volume="", size1=""))),
        source_filename="HighLevelOptionSentiment_Complete_2026-07-15.zip",
        completeness="complete",
        known_at=dt.datetime(2026, 7, 16, 9, tzinfo=dt.UTC),
    )

    assert parsed.trade_date == dt.date(2026, 7, 15)
    assert parsed.rows[0].avg_call_size is None
    assert parsed.rows[0].cust_volume is None
    assert parsed.rows[0].size1 is None


def test_parser_rejects_schema_drift_and_duplicate_underlyings() -> None:
    malformed = _csv(_row()).decode().replace("trade_date", "date", 1).encode()
    with pytest.raises(ValueError, match="schema"):
        parse_cboe_option_sentiment(
            malformed,
            source_filename="sample.csv",
            completeness="sample",
            known_at=dt.datetime.now(dt.UTC),
        )

    with pytest.raises(ValueError, match="duplicate"):
        parse_cboe_option_sentiment(
            _csv(_row(), _row()),
            source_filename="sample.csv",
            completeness="sample",
            known_at=dt.datetime.now(dt.UTC),
        )


def test_parser_rejects_broken_aggregates_and_naive_known_at() -> None:
    with pytest.raises(ValueError, match="total_volume"):
        parse_cboe_option_sentiment(
            _csv(_row(total_volume="99")),
            source_filename="sample.csv",
            completeness="sample",
            known_at=dt.datetime.now(dt.UTC),
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_cboe_option_sentiment(
            _csv(_row()),
            source_filename="sample.csv",
            completeness="sample",
            known_at=dt.datetime(2026, 7, 16, 9),
        )


def test_parser_rejects_path_members_in_vendor_archive() -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("nested/data.csv", _csv(_row()))

    with pytest.raises(ValueError, match="must not contain a path"):
        parse_cboe_option_sentiment(
            output.getvalue(),
            source_filename="sample.zip",
            completeness="sample",
            known_at=dt.datetime.now(dt.UTC),
        )


def test_numeric_parser_preserves_large_integers_and_rejects_non_finite_values() -> None:
    assert _number("total_volume", "9007199254740993", row_number=2) == 9007199254740993
    with pytest.raises(ValueError, match="invalid spot_chg"):
        _number("spot_chg", "NaN", row_number=2)
