from __future__ import annotations

import datetime as dt
import uuid

import pytest

from bulls.core.models import IntradayBar, IntradayQuoteObservation, QuoteSnapshot
from bulls.market_data import Quote
from ingestion.intraday import (
    _bars_for_inserted_observations,
    _observation_key,
    derive_capture_rows,
    expected_capture_slots,
    is_expected_capture_time,
)


def _quote(
    *,
    observed_at: dt.datetime,
    market: str = "DSE",
    volume: int = 1_000,
    trades: int = 20,
    turnover_mn: float | None = 0.12,
    ltp: float = 120,
) -> Quote:
    return Quote(
        market=market,
        code="AAA",
        ltp=ltp,
        change=1,
        change_pct=0.84,
        open=None,
        high=121,
        low=118,
        close=120,
        prev_close=119,
        volume=volume,
        trades=trades,
        turnover_mn=turnover_mn,
        as_of=observed_at,
        is_delayed=True,
    )


def _snapshot(quote: Quote) -> QuoteSnapshot:
    return QuoteSnapshot(**quote.model_dump())


def test_dse_capture_schedule_includes_the_final_delayed_close_read() -> None:
    assert expected_capture_slots(dt.date(2026, 7, 19)) == 20
    assert is_expected_capture_time(dt.datetime(2026, 7, 19, 8, 45, tzinfo=dt.UTC))
    assert not is_expected_capture_time(dt.datetime(2026, 7, 19, 9, 0, tzinfo=dt.UTC))


def test_first_capture_is_a_labelled_baseline_with_real_session_vwap() -> None:
    quote = _quote(observed_at=dt.datetime(2026, 7, 19, 4, 0, tzinfo=dt.UTC))
    rows = derive_capture_rows([quote], {}, source_snapshot_id=uuid.uuid4())

    observation = rows.observations[0]
    bar = rows.bars[0]
    assert observation["sequence_status"] == "baseline"
    assert observation["session_vwap"] == 120
    assert observation["time_quality"] == "ingestion_upper_bound"
    assert observation["price_basis"] == "last_trade"
    assert bar["data_quality"] == "baseline"
    assert bar["volume_delta"] is None
    assert bar["interval_vwap"] is None
    assert bar["open"] == bar["high"] == bar["low"] == bar["close"] == quote.ltp
    assert bar["price_basis"] == "last_trade"


def test_post_close_zero_ltp_retains_raw_observation_and_uses_labelled_close() -> None:
    quote = _quote(
        observed_at=dt.datetime(2026, 7, 19, 8, 45, tzinfo=dt.UTC),
        ltp=0,
    )

    rows = derive_capture_rows([quote], {}, source_snapshot_id=uuid.uuid4())

    assert rows.observations[0]["ltp"] == 0
    assert rows.observations[0]["price_basis"] == "official_close"
    assert rows.bars[0]["close"] == quote.close
    assert rows.bars[0]["price_basis"] == "official_close"
    assert rows.official_close_count == 1
    assert rows.unavailable_price_count == 0


def test_unpriced_no_trade_quote_is_retained_without_manufacturing_a_bar() -> None:
    quote = _quote(
        observed_at=dt.datetime(2026, 7, 19, 8, 45, tzinfo=dt.UTC),
        ltp=0,
    ).model_copy(update={"high": 0, "low": 0, "close": 0, "volume": 0, "trades": 0})

    rows = derive_capture_rows([quote], {}, source_snapshot_id=uuid.uuid4())

    assert rows.observations[0]["price_basis"] == "unavailable"
    assert rows.bars == []
    assert rows.official_close_count == 0
    assert rows.unavailable_price_count == 1


def test_later_capture_derives_counter_deltas_without_reusing_session_totals() -> None:
    first = _quote(observed_at=dt.datetime(2026, 7, 19, 4, 0, tzinfo=dt.UTC))
    second = _quote(
        observed_at=dt.datetime(2026, 7, 19, 4, 15, tzinfo=dt.UTC),
        volume=1_500,
        trades=28,
        turnover_mn=0.1825,
        ltp=121,
    )

    rows = derive_capture_rows(
        [second],
        {"AAA": _snapshot(first)},
        source_snapshot_id=uuid.uuid4(),
    )

    observation = rows.observations[0]
    bar = rows.bars[0]
    assert observation["sequence_status"] == "advanced"
    assert bar["volume_delta"] == 500
    assert bar["trades_delta"] == 8
    assert bar["turnover_delta_mn"] == pytest.approx(0.0625)
    assert bar["interval_vwap"] == 125
    assert bar["data_quality"] == "complete_delta"


def test_counter_regression_is_retained_and_never_converted_to_negative_flow() -> None:
    first = _quote(
        observed_at=dt.datetime(2026, 7, 19, 4, 0, tzinfo=dt.UTC),
        volume=2_000,
        trades=40,
        turnover_mn=0.24,
    )
    regressed = _quote(
        observed_at=dt.datetime(2026, 7, 19, 4, 15, tzinfo=dt.UTC),
        volume=1_900,
        trades=39,
        turnover_mn=0.23,
    )

    rows = derive_capture_rows(
        [regressed],
        {"AAA": _snapshot(first)},
        source_snapshot_id=uuid.uuid4(),
    )

    assert rows.regression_count == 1
    assert rows.observations[0]["sequence_status"] == "regressed"
    assert rows.bars[0]["data_quality"] == "counter_regression"
    assert rows.bars[0]["volume_delta"] is None
    assert rows.bars[0]["turnover_delta_mn"] is None


def test_intraday_capture_refuses_cross_market_data() -> None:
    with pytest.raises(ValueError, match="cannot accept"):
        derive_capture_rows(
            [
                _quote(
                    observed_at=dt.datetime(2026, 7, 19, 14, 0, tzinfo=dt.UTC),
                    market="US",
                )
            ],
            {},
            source_snapshot_id=uuid.uuid4(),
        )


def test_intraday_tables_declare_date_range_partitioning() -> None:
    assert (
        IntradayQuoteObservation.__table__.dialect_options["postgresql"]["partition_by"]
        == "RANGE (session_date)"
    )
    assert (
        IntradayBar.__table__.dialect_options["postgresql"]["partition_by"]
        == "RANGE (session_date)"
    )


def test_duplicate_observation_cannot_increment_the_sampled_bar_projection() -> None:
    quote = _quote(observed_at=dt.datetime(2026, 7, 19, 4, 0, tzinfo=dt.UTC))
    rows = derive_capture_rows([quote], {}, source_snapshot_id=uuid.uuid4())

    assert _bars_for_inserted_observations(rows.bars, set()) == []
    assert (
        _bars_for_inserted_observations(
            rows.bars,
            {_observation_key(rows.observations[0])},
        )
        == rows.bars
    )
