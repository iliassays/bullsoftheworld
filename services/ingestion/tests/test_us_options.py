from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest

from bulls.market_data.options.cboe_sentiment import (
    CBOE_OPTION_SENTIMENT_SCHEMA_VERSION,
    CboeOptionSentimentRecord,
)
from ingestion.us_options.evaluation import (
    EvaluationDelivery,
    _prepare_frame,
    evaluate_option_sentiment,
    expected_us_sessions,
)
from ingestion.us_options.parquet import option_sentiment_parquet
from ingestion.us_options.pipeline import (
    _read_bounded_regular_file,
    entitlement_allows_internal_research,
)
from ingestion.us_options.quality import SecurityAlias, normalize_option_sentiment
from ingestion.us_options.storage import LocalImmutableObjectStore


def _record(
    symbol: str = "AAPL",
    security_type: str = "S",
    trade_date: dt.date = dt.date(2026, 7, 15),
) -> CboeOptionSentimentRecord:
    values = {
        field: 0
        for field in CboeOptionSentimentRecord.model_fields
        if field
        not in {
            "trade_date",
            "underlying_symbol",
            "underlying_security_type",
            "avg_call_size",
            "avg_put_size",
            "cust_volume",
            "firm_volume",
            "mkt_mkr_volume",
            "implied_borrow",
            "norm_25d_skew_30",
            "iv30",
            "iv90",
            "hv20",
            "size1",
            "size2_10",
            "size11_100",
            "size101_500",
            "size501_1000",
            "size1001up",
        }
    }
    values.update(
        {
            "trade_date": trade_date,
            "underlying_symbol": symbol,
            "underlying_security_type": security_type,
            "spot_close": 100,
            "split_adj_close": 100,
        }
    )
    return CboeOptionSentimentRecord.model_validate(values)


def test_quality_gate_separates_stock_identity_from_etf_absence() -> None:
    rows, report, fingerprint = normalize_option_sentiment(
        [_record(), _record("SPY", "E")],
        securities=[SecurityAlias("AAPL", ("AAPL",))],
        completeness="sample",
        minimum_identity_coverage=0.95,
    )

    assert report.passed
    assert report.stock_identity_coverage == 1
    assert report.etf_rows == 1
    assert rows[1].identity_status == "excluded_etf"
    assert len(fingerprint) == 64
    assert option_sentiment_parquet(rows).startswith(b"PAR1")


def test_quality_gate_rejects_preliminary_and_low_identity_coverage() -> None:
    _, report, _ = normalize_option_sentiment(
        [_record("UNKNOWN")],
        securities=[],
        completeness="preliminary",
        minimum_identity_coverage=0.95,
    )

    assert not report.passed
    assert len(report.reasons) == 2


def test_entitlement_is_fail_closed_for_scope_retention_and_dates() -> None:
    entitlement = SimpleNamespace(
        status="approved",
        internal_research_allowed=True,
        retention_allowed=True,
        valid_from=dt.date(2026, 1, 1),
        valid_until=dt.date(2026, 12, 31),
    )

    assert entitlement_allows_internal_research(
        entitlement, on_date=dt.date(2026, 7, 15)
    )
    entitlement.retention_allowed = False
    assert not entitlement_allows_internal_research(
        entitlement, on_date=dt.date(2026, 7, 15)
    )


def test_local_object_store_is_idempotent_and_rejects_collisions(tmp_path) -> None:
    store = LocalImmutableObjectStore(tmp_path)
    first = store.put(
        key="us/options/raw/abc.csv",
        payload=b"first",
        content_type="text/csv",
    )
    second = store.put(
        key="us/options/raw/abc.csv",
        payload=b"first",
        content_type="text/csv",
    )
    assert first == second
    assert store.get(key="us/options/raw/abc.csv", max_bytes=5) == b"first"
    with pytest.raises(ValueError, match="exceeds"):
        store.get(key="us/options/raw/abc.csv", max_bytes=4)

    try:
        store.put(
            key="us/options/raw/abc.csv",
            payload=b"second",
            content_type="text/csv",
        )
    except RuntimeError as exc:
        assert "collision" in str(exc)
    else:
        raise AssertionError("immutable collision was not rejected")


def test_operator_input_reader_rejects_symlinks_and_special_files(tmp_path) -> None:
    source = tmp_path / "delivery.csv"
    source.write_bytes(b"content")
    link = tmp_path / "linked.csv"
    link.symlink_to(source)

    with pytest.raises(ValueError, match="safely open"):
        _read_bounded_regular_file(link)

    with pytest.raises(ValueError, match="regular file"):
        _read_bounded_regular_file(Path("/dev/null"))


def _delivery(trade_date: dt.date) -> EvaluationDelivery:
    rows, report, _ = normalize_option_sentiment(
        [_record(trade_date=trade_date)],
        securities=[SecurityAlias("AAPL", ("AAPL",))],
        completeness="complete",
        minimum_identity_coverage=0.95,
    )
    assert report.passed
    return EvaluationDelivery(
        snapshot_id=trade_date.isoformat(),
        trade_date=trade_date,
        effective_at=dt.datetime.combine(
            trade_date,
            dt.time(20),
            tzinfo=dt.UTC,
        ),
        known_at=dt.datetime.combine(
            trade_date + dt.timedelta(days=1),
            dt.time(10),
            tzinfo=dt.UTC,
        ),
        delivery_mode="historical",
        frame=_prepare_frame(option_sentiment_parquet(rows), trade_date=trade_date),
    )


def test_one_year_evaluator_uses_verified_calendar_and_passes_complete_fixture() -> None:
    sessions = expected_us_sessions(dt.date(2025, 7, 1), dt.date(2025, 7, 4))
    assert sessions == [
        dt.date(2025, 7, 1),
        dt.date(2025, 7, 2),
        dt.date(2025, 7, 3),
    ]
    report = evaluate_option_sentiment(
        (_delivery(day) for day in sessions),
        start_date=sessions[0],
        end_date=dt.date(2025, 7, 4),
        input_fingerprint="a" * 64,
        rejected_delivery_count=0,
        ignored_noncomplete_delivery_count=0,
        superseded_revision_count=0,
        schema_versions=[CBOE_OPTION_SENTIMENT_SCHEMA_VERSION],
        normalization_versions=["atlas-option-sentiment-normalization-v1"],
        identity_versions=["us-security-master-options-alias-v1"],
        minimum_identity_coverage=0.95,
        generated_at=dt.datetime(2026, 7, 16, tzinfo=dt.UTC),
    )

    assert report.decision == "ready_for_phase_b_review"
    assert report.calendar_coverage == 1
    assert report.stock_identity_coverage == 1
    assert report.delivery_modes == {"historical": 3}
    assert report.subscription_delivery_lag_hours is None
    assert all(gate.passed for gate in report.gates)


def test_evaluator_refuses_to_promote_incomplete_or_rejected_history() -> None:
    sessions = expected_us_sessions(dt.date(2025, 7, 1), dt.date(2025, 7, 3))
    report = evaluate_option_sentiment(
        [_delivery(sessions[0])],
        start_date=sessions[0],
        end_date=sessions[-1],
        input_fingerprint="b" * 64,
        rejected_delivery_count=1,
        ignored_noncomplete_delivery_count=0,
        superseded_revision_count=0,
        schema_versions=[CBOE_OPTION_SENTIMENT_SCHEMA_VERSION],
        normalization_versions=["atlas-option-sentiment-normalization-v1"],
        identity_versions=["us-security-master-options-alias-v1"],
        minimum_identity_coverage=0.95,
    )

    assert report.decision == "insufficient_data"
    assert report.missing_sessions == sessions[1:]
    assert {gate.name for gate in report.gates if not gate.passed} >= {
        "one_year_session_depth",
        "calendar_coverage",
        "rejected_deliveries",
    }
