import datetime as dt

from bulls.analytics.model_certification import (
    DataFoundationAttestation,
    certify_data_foundation,
    run_engine_certification,
)
from bulls.analytics.research_strategy import (
    BenchmarkPoint,
    BenchmarkSeries,
    StrategyBar,
    StrategySecurity,
)


def _security() -> StrategySecurity:
    dates = [dt.date(2025, 1, 6), dt.date(2025, 1, 7)]
    return StrategySecurity(
        code="KNOWN",
        bars=[
            StrategyBar(
                date=date,
                open=10,
                high=11,
                low=9,
                close=10,
                volume=1_000,
            )
            for date in dates
        ],
    )


def _benchmark() -> BenchmarkSeries:
    return BenchmarkSeries(
        key="control",
        label="Control",
        points=[
            BenchmarkPoint(date=dt.date(2025, 1, 6), close=100),
            BenchmarkPoint(date=dt.date(2025, 1, 7), close=101),
        ],
    )


def test_engine_known_answer_certification_passes() -> None:
    report = run_engine_certification()

    assert report.passed
    assert all(check.passed for check in report.checks)
    assert {check.key for check in report.checks} == {
        "next_session_execution",
        "known_answer_nav",
        "independent_benchmark",
        "cost_accounting",
        "sell_before_buy_funding",
        "implicit_benchmark_blocks_promotion",
    }


def test_data_foundation_fails_closed_without_evidence_attestations() -> None:
    report = certify_data_foundation(
        securities=[_security()],
        benchmark=_benchmark(),
        attestation=DataFoundationAttestation(evidence_reference="fixture-audit"),
    )

    assert not report.passed
    assert all(
        check.passed
        for check in report.checks
        if check.key
        in {
            "unique_security_series",
            "unique_bar_keys",
            "ohlc_integrity",
            "independent_benchmark_coverage",
        }
    )
    assert not next(
        check for check in report.checks if check.key == "inactive_and_delisted_history"
    ).passed


def test_data_foundation_passes_only_with_complete_structural_and_attested_evidence() -> None:
    report = certify_data_foundation(
        securities=[_security()],
        benchmark=_benchmark(),
        attestation=DataFoundationAttestation(
            evidence_reference="fixture-audit",
            inactive_and_delisted_history_complete=True,
            historical_universe_membership_complete=True,
            point_in_time_fundamentals_complete=True,
            corporate_action_adjustments_complete=True,
            stable_security_identifiers_complete=True,
        ),
    )

    assert report.passed


def test_data_foundation_rejects_invalid_ohlc() -> None:
    security = _security()
    security.bars[0] = security.bars[0].model_copy(update={"high": 9.5})

    report = certify_data_foundation(
        securities=[security],
        benchmark=_benchmark(),
        attestation=DataFoundationAttestation(evidence_reference="fixture-audit"),
    )

    check = next(item for item in report.checks if item.key == "ohlc_integrity")
    assert not check.passed
