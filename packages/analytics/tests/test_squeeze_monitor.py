from __future__ import annotations

import datetime as dt

from bulls.analytics.squeeze_monitor import (
    METHODOLOGY_VERSION,
    SqueezeBar,
    SqueezeInputs,
    evaluate_compression_breakout,
    evaluate_failed_breakdown,
    evaluate_families,
    evaluate_supply_constrained,
    should_archive_transition,
)


def _bars(
    prices: list[tuple[float, float, float, float]],
    *,
    volume: float = 500_000,
    volumes: list[float] | None = None,
):
    start = dt.date(2026, 1, 5)
    return [
        SqueezeBar(
            date=start + dt.timedelta(days=index),
            open=o,
            high=h,
            low=lo,
            close=c,
            volume=volumes[index] if volumes is not None else volume,
        )
        for index, (o, h, lo, c) in enumerate(prices)
    ]


def _flat(sessions: int, price: float, *, wobble: float = 0.4):
    return [(price, price + wobble, price - wobble, price) for _ in range(sessions)]


def _inputs(**overrides) -> SqueezeInputs:
    # 120 sessions: a rise to 100 then a tightening base just under the high.
    ramp = [(60 + i * 0.5, 61 + i * 0.5, 59 + i * 0.5, 60.5 + i * 0.5) for i in range(80)]
    base = _flat(24, 99.0)
    defaults = dict(
        market="US",
        code="TEST",
        bars=_bars(ramp + base),
        last_close=99.0,
        sma_50=95.0,
        sma_200=80.0,
        pct_from_52w_high=-2.0,
        relative_volume=1.0,
        rel_volume_5d=0.8,
    )
    defaults.update(overrides)
    return SqueezeInputs(**defaults)


def test_compression_base_with_contraction_is_trigger_ready() -> None:
    result = evaluate_compression_breakout(_inputs())

    assert result.state == "trigger_ready"
    assert result.trigger_price == 99.4  # base high of the last 20 flat sessions
    assert result.invalidation_price == 98.6
    assert result.risk_per_share is not None
    # 2R geometry, explicitly not a forecast.
    assert result.planning_objective_price == round(99.4 + 2 * (99.4 - 98.6), 6)
    assert result.methodology_version == METHODOLOGY_VERSION


def test_breakout_with_participation_confirms() -> None:
    ramp = [(60 + i * 0.5, 61 + i * 0.5, 59 + i * 0.5, 60.5 + i * 0.5) for i in range(80)]
    prices = ramp + _flat(21, 99.0) + [(99.0, 102.0, 98.8, 101.5)] * 3
    # Volume expands on the breakout bars themselves, which is what confirmation means.
    volumes = [500_000] * (len(prices) - 3) + [1_000_000] * 3
    result = evaluate_compression_breakout(
        _inputs(bars=_bars(prices, volumes=volumes), last_close=101.5, relative_volume=2.1)
    )

    assert result.state == "confirmed"
    assert "2.0x the base" in result.reason


def test_high_volume_breakout_without_contraction_is_not_confirmed() -> None:
    prices = _flat(101, 99.0) + [(99.0, 102.0, 98.8, 101.5)] * 3
    volumes = [500_000] * (len(prices) - 3) + [1_000_000] * 3

    result = evaluate_compression_breakout(
        _inputs(
            bars=_bars(prices, volumes=volumes),
            last_close=101.5,
            relative_volume=2.0,
        )
    )

    assert result.state == "watch"
    assert result.state != "confirmed"


def test_high_volume_breakout_far_from_52_week_high_is_not_confirmed() -> None:
    ramp = [(60 + i * 0.5, 61 + i * 0.5, 59 + i * 0.5, 60.5 + i * 0.5) for i in range(80)]
    prices = ramp + _flat(21, 99.0) + [(99.0, 102.0, 98.8, 101.5)] * 3
    volumes = [500_000] * (len(prices) - 3) + [1_000_000] * 3

    result = evaluate_compression_breakout(
        _inputs(
            bars=_bars(prices, volumes=volumes),
            last_close=101.5,
            relative_volume=2.0,
            pct_from_52w_high=-25.0,
        )
    )

    assert result.state == "none"


def test_low_volume_breakout_is_not_confirmed_by_an_unrelated_volume_spike_today() -> None:
    """The breakout session must carry the volume, not merely the day we happen to look.

    Pairing "some close in the last 3 sessions cleared the base" with today's relative volume
    confirmed weak breakouts whenever an unrelated spike landed today.
    """

    ramp = [(60 + i * 0.5, 61 + i * 0.5, 59 + i * 0.5, 60.5 + i * 0.5) for i in range(80)]
    prices = ramp + _flat(21, 99.0) + [(99.0, 102.0, 98.8, 101.5)] + [(101.5, 102.0, 101.0, 101.6)] * 2
    # The breakout bar traded BELOW the base average; only today is busy, for other reasons.
    volumes = [500_000] * (len(prices) - 3) + [400_000] + [500_000] * 2
    result = evaluate_compression_breakout(
        _inputs(bars=_bars(prices, volumes=volumes), last_close=101.6, relative_volume=3.0)
    )

    assert result.state != "confirmed"


def test_downtrend_is_ineligible() -> None:
    result = evaluate_compression_breakout(_inputs(sma_200=120.0))

    assert result.state == "none"


def test_archived_trigger_that_gives_way_becomes_failed() -> None:
    result = evaluate_compression_breakout(
        _inputs(prior_state="confirmed", prior_trigger_price=105.0, last_close=99.0)
    )

    assert result.state == "failed"
    assert "97%" in result.reason


def test_extension_is_reported_as_too_late() -> None:
    result = evaluate_compression_breakout(_inputs(sma_50=70.0, last_close=99.0))

    assert result.state == "exhausted"
    assert "Too extended" in result.reason


def test_failed_breakdown_reclaim_confirms_with_honest_naming() -> None:
    steady = _flat(100, 50.0)
    undercut = [(50.0, 50.2, 47.0, 48.0)] * 3  # support ~49.6 broken
    reclaim = [(48.0, 51.5, 47.9, 51.0)] * 2
    result = evaluate_failed_breakdown(
        _inputs(
            bars=_bars(steady + undercut + reclaim),
            last_close=51.0,
            relative_volume=1.6,
            sma_200=45.0,
            sma_50=49.0,
        )
    )

    assert result.state == "confirmed"
    assert "short-positioning evidence does not exist" in result.reason.lower()
    assert result.invalidation_price == 47.0


def test_failed_breakdown_marks_failure_only_for_a_previously_live_setup() -> None:
    steady = _flat(100, 50.0)
    # Undercut to a 44.0 low, then a session closing BELOW that low: the published invalidation.
    breakdown = [(50.0, 50.0, 46.0, 46.2)] * 3 + [(46.0, 46.1, 44.0, 44.5)] * 2
    breakdown += [(44.0, 44.2, 42.0, 42.5)]
    bars = _bars(steady + breakdown)
    common = dict(bars=bars, last_close=42.5, sma_200=40.0, sma_50=44.0)

    was_live = evaluate_failed_breakdown(_inputs(**common, prior_state="forming"))
    assert was_live.state == "failed"
    # Failure is judged on the level the card publishes, not on a different internal threshold.
    assert was_live.invalidation_price == 44.0

    # A stock that was never a setup and is simply falling must not enter the archive as a
    # "failed setup" — it was never a reversal candidate.
    never_a_setup = evaluate_failed_breakdown(_inputs(**common))
    assert never_a_setup.state == "none"
    assert "active breakdown" in never_a_setup.reason


def test_failed_breakdown_requires_the_shared_uptrend_gate() -> None:
    """A bounce inside a downtrend is not this family's setup."""

    steady = _flat(100, 50.0)
    undercut = [(50.0, 50.2, 47.0, 48.0)] * 3
    reclaim = [(48.0, 51.5, 47.9, 51.0)] * 2
    result = evaluate_failed_breakdown(
        _inputs(
            bars=_bars(steady + undercut + reclaim),
            last_close=51.0,
            relative_volume=1.6,
            sma_200=80.0,  # price is far below its 200-session average
        )
    )

    assert result.state == "none"


def test_supply_constrained_requires_verified_scarcity() -> None:
    without_float = evaluate_supply_constrained(_inputs(market="DSE"))
    assert without_float.state == "none"
    assert any("free float" in item.lower() for item in without_float.missing_evidence)

    scarce = evaluate_supply_constrained(
        _inputs(market="DSE", market_cap_mn=10_000, free_float_cap_mn=2_500)
    )
    assert scarce.state == "trigger_ready"
    assert any("supply scarcity" in item.lower() for item in scarce.supporting_evidence)
    # DSE data-quality caveat is always present.
    assert any("corporate-action" in item for item in scarce.data_quality)


def test_supply_constrained_breakout_inherits_compression_gate() -> None:
    prices = _flat(101, 99.0) + [(99.0, 102.0, 98.8, 101.5)] * 3
    volumes = [500_000] * (len(prices) - 3) + [1_000_000] * 3

    result = evaluate_supply_constrained(
        _inputs(
            market="DSE",
            bars=_bars(prices, volumes=volumes),
            last_close=101.5,
            relative_volume=2.0,
            market_cap_mn=10_000,
            free_float_cap_mn=2_500,
        )
    )

    assert result.state == "watch"
    assert result.state != "confirmed"


def test_short_marked_share_is_supporting_context_with_exact_disclaimer() -> None:
    result = evaluate_compression_breakout(_inputs(short_marked_share_5d=0.72))

    note = next(
        item for item in result.supporting_evidence if "Short-marked" in item
    )
    assert "not short interest" in note
    assert "cannot establish positioning" in note


def test_no_family_ever_says_short_squeeze() -> None:
    for assessment in evaluate_families(
        _inputs(market="DSE", market_cap_mn=10_000, free_float_cap_mn=2_000, sponsor_pct=60)
    ):
        blob = " ".join(
            [
                assessment.reason,
                *assessment.supporting_evidence,
                *assessment.counter_evidence,
                *assessment.data_quality,
            ]
        ).lower()
        assert "short squeeze" not in blob


def test_standalone_terminal_assessment_does_not_start_an_episode() -> None:
    assert not should_archive_transition(state="exhausted", prior_state="none")
    assert not should_archive_transition(state="failed", prior_state="exhausted")
    assert should_archive_transition(state="forming", prior_state="none")
    assert should_archive_transition(state="exhausted", prior_state="confirmed")


def test_dilution_and_insider_selling_surface_as_counter_evidence() -> None:
    result = evaluate_compression_breakout(
        _inputs(recent_dilution_filing=True, insider_net_selling_30d=True)
    )

    assert any("dilution" in item.lower() for item in result.counter_evidence)
    assert any("insider" in item.lower() for item in result.counter_evidence)


def test_dilution_risk_reports_unassessed_when_the_archive_is_unavailable() -> None:
    """A missing dataset must read as unknown, never as an absent risk.

    The financing-filing forms (S-1/S-3/424B) are not ingested, so this check had nothing to
    search. While the field was a plain bool it defaulted to False and every card silently
    implied no dilution risk had been found -- absence of a warning reading as absence of risk,
    which is the omit-over-mislead failure the module exists to prevent.
    """
    inputs = _inputs(recent_dilution_filing=None)
    assessment = evaluate_compression_breakout(inputs)
    assert any("unassessed rather than absent" in note for note in assessment.data_quality)
    assert not any("financing/dilution filing" in note for note in assessment.counter_evidence)


def test_dilution_risk_stays_silent_when_the_archive_was_searched_and_found_nothing() -> None:
    inputs = _inputs(recent_dilution_filing=False)
    assessment = evaluate_compression_breakout(inputs)
    assert not any("dilution" in note.lower() for note in assessment.data_quality)
    assert not any("financing/dilution filing" in note for note in assessment.counter_evidence)


def test_dilution_risk_is_counter_evidence_when_a_filing_exists() -> None:
    inputs = _inputs(recent_dilution_filing=True)
    assessment = evaluate_compression_breakout(inputs)
    assert any("financing/dilution filing" in note for note in assessment.counter_evidence)
