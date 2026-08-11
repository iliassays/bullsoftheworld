from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ingestion.research_condition_evidence import (
    CalibrationCollector,
    ExistingConditionEvidence,
    compile_condition_evidence,
    condition_alert_text,
)


@dataclass(frozen=True)
class Bar:
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float


def _bars(count: int = 80, *, expansion_at: int | None = None) -> list[Bar]:
    output: list[Bar] = []
    for index in range(count):
        close = 100.0 + index * 0.15
        output.append(
            Bar(
                date=dt.date(2026, 1, 1) + dt.timedelta(days=index),
                open=close - 0.1,
                high=close + 0.5,
                low=close - 0.5,
                close=close,
                volume=2_000.0 if index == expansion_at else 1_000.0,
            )
        )
    return output


def test_only_same_day_transition_can_be_forward_and_alertable() -> None:
    history = _bars(expansion_at=79)
    compiled = compile_condition_evidence(
        market="DSE",
        code="TEST",
        bars=history,
        forward_date=history[-1].date,
    )

    assert len(compiled.forward_observations) == 1
    observation = compiled.forward_observations[0]
    assert observation["condition_key"] == "participation_expansion"
    assert observation["as_of_date"] == history[-1].date
    assert observation["evidence_mode"] == "forward"
    assert all(
        row["evidence_mode"] == "reconstructed"
        for row in compiled.rows
        if row["as_of_date"] != history[-1].date
    )


def test_historical_run_cannot_manufacture_forward_observations() -> None:
    compiled = compile_condition_evidence(
        market="US",
        code="TEST",
        bars=_bars(expansion_at=79),
    )

    assert compiled.forward_observations == ()
    assert all(row["evidence_mode"] == "reconstructed" for row in compiled.rows)


def test_existing_forward_mode_survives_later_reconstruction() -> None:
    history = _bars(expansion_at=70)
    identity = ("participation_expansion", "1.0.0", history[70].date)
    compiled = compile_condition_evidence(
        market="US",
        code="TEST",
        bars=history,
        existing={identity: ExistingConditionEvidence("forward", {})},
    )

    modes = {
        outcome.observed_date: mode
        for mode, outcome in compiled.outcomes
        if outcome.condition_key == "participation_expansion"
    }
    assert modes[history[70].date] == "forward"


def test_calibration_keeps_forward_and_reconstructed_samples_separate() -> None:
    history = _bars(expansion_at=79)
    historical = compile_condition_evidence(
        market="DSE",
        code="OLD",
        bars=_bars(expansion_at=70),
    )
    current = compile_condition_evidence(
        market="DSE",
        code="NEW",
        bars=history,
        forward_date=history[-1].date,
    )
    collector = CalibrationCollector()
    collector.add(historical)
    collector.add(current)

    rows = collector.rows("DSE", history[-1].date)
    modes = {
        row["evidence_mode"] for row in rows if row["condition_key"] == "participation_expansion"
    }
    assert modes == {"forward", "reconstructed"}
    assert all(row["point_in_time_complete"] is False for row in rows)
    assert all("not" in row["warning_text"] for row in rows)


def test_condition_alert_copy_is_research_only_and_market_localized() -> None:
    title, body = condition_alert_text("DSE", "GP", "trend_alignment", dt.date(2026, 8, 11))
    assert title["en"].startswith("$GP")
    assert "bn" in title and "bn" in body
    assert "not a trade signal or order" in body["en"]

    us_title, us_body = condition_alert_text("US", "AAPL", "trend_alignment", dt.date(2026, 8, 11))
    assert set(us_title) == {"en"}
    assert set(us_body) == {"en"}
