"""Tests for System C: the factor sleeve and the nulls it must beat (Phase 12 / 13.3.4)."""

from __future__ import annotations

import datetime as dt

import pytest

from bulls.analytics.factor_sleeve import (
    FundamentalFact,
    FundamentalObservation,
    PricePoint,
    SecurityFactorInputs,
    SleevePolicy,
    compute_factor_scores,
    equal_weight_null,
    point_in_time_factor_fundamentals,
    point_in_time_fundamentals,
    rank_universe,
    single_factor_null,
    sleeve_weights,
)


def _fact(code: str, metric: str, value: float, period_end: str, filed_at: str) -> FundamentalFact:
    return FundamentalFact(
        code=code, metric=metric, value=value,
        period_end=dt.date.fromisoformat(period_end), filed_at=dt.date.fromisoformat(filed_at),
    )


def _observation(
    metric: str,
    value: float,
    period_end: str,
    known_at: str,
    *,
    period_type: str = "instant",
    period_start: str | None = None,
    accession: str = "0001",
) -> FundamentalObservation:
    return FundamentalObservation(
        code="AAA",
        metric=metric,
        value=value,
        unit="USD",
        period_start=dt.date.fromisoformat(period_start) if period_start else None,
        period_end=dt.date.fromisoformat(period_end),
        period_type=period_type,
        known_at=dt.datetime.fromisoformat(known_at),
        accession_number=accession,
    )


def _prices(*, start: float, growth: float, n: int = 300, jitter: float = 0.0) -> list[PricePoint]:
    base = dt.date(2024, 1, 1)
    points = []
    price = start
    for i in range(n):
        price *= 1 + growth + (jitter if i % 2 == 0 else -jitter)
        points.append(PricePoint(date=base + dt.timedelta(days=i), close=round(price, 4)))
    return points


# --- point-in-time resolution ----------------------------------------------------------------


def test_unpublished_facts_are_invisible() -> None:
    facts = [_fact("AAA", "equity", 100.0, "2025-12-31", "2026-02-10")]
    # As of January, a December quarter filed in February is simply not knowable.
    assert point_in_time_fundamentals(facts, as_of=dt.date(2026, 1, 15)) == {}
    assert point_in_time_fundamentals(facts, as_of=dt.date(2026, 2, 10))["AAA"]["equity"] == 100.0


def test_most_recent_published_period_wins() -> None:
    facts = [
        _fact("AAA", "equity", 100.0, "2025-06-30", "2025-08-01"),
        _fact("AAA", "equity", 120.0, "2025-09-30", "2025-11-01"),
    ]
    resolved = point_in_time_fundamentals(facts, as_of=dt.date(2025, 12, 1))
    assert resolved["AAA"]["equity"] == 120.0
    # Before the newer filing existed, the older period is still the best available.
    assert point_in_time_fundamentals(facts, as_of=dt.date(2025, 9, 1))["AAA"]["equity"] == 100.0


def test_restatement_never_leaks_backwards() -> None:
    # The same period filed twice: first disclosure is what a signal could have used.
    facts = [
        _fact("AAA", "equity", 100.0, "2025-06-30", "2025-08-01"),
        _fact("AAA", "equity", 999.0, "2025-06-30", "2026-03-01"),  # later restatement
    ]
    resolved = point_in_time_fundamentals(facts, as_of=dt.date(2026, 6, 1))
    assert resolved["AAA"]["equity"] == 100.0


def test_multiple_securities_and_metrics_resolve_independently() -> None:
    facts = [
        _fact("AAA", "equity", 10.0, "2025-06-30", "2025-08-01"),
        _fact("AAA", "net_income", 2.0, "2025-06-30", "2025-08-01"),
        _fact("BBB", "equity", 50.0, "2025-06-30", "2025-08-05"),
    ]
    resolved = point_in_time_fundamentals(facts, as_of=dt.date(2025, 12, 1))
    assert resolved["AAA"] == {"equity": 10.0, "net_income": 2.0}
    assert resolved["BBB"] == {"equity": 50.0}


def test_append_only_revision_changes_only_later_rebalances() -> None:
    observations = [
        _observation("equity", 100.0, "2025-12-31", "2026-02-01T12:00:00+00:00"),
        _observation(
            "equity",
            80.0,
            "2025-12-31",
            "2026-04-01T12:00:00+00:00",
            accession="0002",
        ),
    ]

    before = point_in_time_factor_fundamentals(
        observations, as_of=dt.date(2026, 3, 1)
    )
    after = point_in_time_factor_fundamentals(
        observations, as_of=dt.date(2026, 5, 1)
    )

    assert before["AAA"]["equity"] == 100.0
    assert after["AAA"]["equity"] == 80.0


def test_factor_quality_uses_four_standalone_quarters() -> None:
    observations = [
        _observation("equity", 200.0, "2025-12-31", "2026-02-01T00:00:00+00:00"),
        *[
            _observation(
                "net_income",
                value,
                period_end,
                known_at,
                period_type="quarter",
                period_start=period_start,
                accession=f"q{index}",
            )
            for index, (value, period_start, period_end, known_at) in enumerate(
                [
                    (10.0, "2025-01-01", "2025-03-31", "2025-05-01T00:00:00+00:00"),
                    (20.0, "2025-04-01", "2025-06-30", "2025-08-01T00:00:00+00:00"),
                    (30.0, "2025-07-01", "2025-09-30", "2025-11-01T00:00:00+00:00"),
                    (40.0, "2025-10-01", "2025-12-31", "2026-02-01T00:00:00+00:00"),
                ],
                start=1,
            )
        ],
    ]

    resolved = point_in_time_factor_fundamentals(
        observations, as_of=dt.date(2026, 3, 1)
    )

    assert resolved["AAA"]["net_income"] == 100.0


# --- factor computation ------------------------------------------------------------------------


def test_scores_the_four_premia() -> None:
    scores = compute_factor_scores(
        SecurityFactorInputs(
            code="AAA",
            prices=_prices(start=10.0, growth=0.002),
            fundamentals={"equity": 500.0, "net_income": 50.0, "shares_outstanding": 100.0},
            prior_fundamentals={"shares_outstanding": 110.0},
        )
    )
    assert scores.quality == pytest.approx(0.1)  # 50 / 500
    assert scores.value is not None and scores.value > 0
    assert scores.momentum is not None and scores.momentum > 0
    # Share count fell 110 -> 100: a ~9.09% buyback, which must score positively.
    assert scores.low_issuance == pytest.approx(1 - 100 / 110)


def test_dilution_scores_negative() -> None:
    scores = compute_factor_scores(
        SecurityFactorInputs(
            code="AAA", prices=_prices(start=10.0, growth=0.001),
            fundamentals={"shares_outstanding": 120.0},
            prior_fundamentals={"shares_outstanding": 100.0},
        )
    )
    assert scores.low_issuance is not None and scores.low_issuance < 0


def test_negative_equity_is_not_treated_as_cheap() -> None:
    # Negative book value is distress, not a bargain: value and quality must both refuse it.
    scores = compute_factor_scores(
        SecurityFactorInputs(
            code="AAA", prices=_prices(start=10.0, growth=0.001),
            fundamentals={"equity": -200.0, "net_income": 10.0, "shares_outstanding": 100.0},
        )
    )
    assert scores.value is None
    assert scores.quality is None


def test_missing_inputs_yield_none_not_zero() -> None:
    scores = compute_factor_scores(SecurityFactorInputs(code="AAA", prices=[]))
    assert scores.value is None and scores.quality is None
    assert scores.momentum is None and scores.low_issuance is None


def test_momentum_skips_the_most_recent_month() -> None:
    # A stock that rose all year then crashed in the final month keeps positive 12-1 momentum,
    # which is the entire point of the skip.
    prices = _prices(start=10.0, growth=0.004, n=300)
    crashed = prices[:-21] + [
        PricePoint(date=p.date, close=p.close * 0.4) for p in prices[-21:]
    ]
    scores = compute_factor_scores(SecurityFactorInputs(code="AAA", prices=crashed))
    assert scores.momentum is not None and scores.momentum > 0


def test_short_history_has_no_momentum() -> None:
    scores = compute_factor_scores(
        SecurityFactorInputs(code="AAA", prices=_prices(start=10.0, growth=0.001, n=100))
    )
    assert scores.momentum is None


# --- ranking ------------------------------------------------------------------------------------


def _scored(code: str, *, value=0.5, quality=0.1, momentum=0.2, low_issuance=0.0, vol=0.25):
    from bulls.analytics.factor_sleeve import FactorScores

    return FactorScores(
        code=code, value=value, quality=quality, momentum=momentum,
        low_issuance=low_issuance, volatility=vol,
    )


def test_better_factors_rank_higher() -> None:
    ranked = rank_universe([
        _scored("BEST", value=0.9, quality=0.3, momentum=0.5, low_issuance=0.1),
        _scored("WORST", value=0.1, quality=0.01, momentum=-0.2, low_issuance=-0.3),
        _scored("MID", value=0.5, quality=0.15, momentum=0.1, low_issuance=-0.05),
    ])
    assert [r.code for r in ranked] == ["BEST", "MID", "WORST"]
    assert ranked[0].composite > ranked[-1].composite


def test_security_missing_too_many_factors_is_not_ranked() -> None:
    from bulls.analytics.factor_sleeve import FactorScores

    thin = FactorScores(code="THIN", value=0.5)  # only one factor
    ranked = rank_universe([thin, _scored("FULL")], SleevePolicy(minimum_factors=3))
    assert [r.code for r in ranked] == ["FULL"]


def test_partial_factor_coverage_is_diluted_not_discarded() -> None:
    from bulls.analytics.factor_sleeve import FactorScores

    partial = FactorScores(code="PART", value=0.9, quality=0.3, momentum=0.5)
    ranked = rank_universe([partial, _scored("FULL")], SleevePolicy(minimum_factors=3))
    codes = [r.code for r in ranked]
    assert "PART" in codes
    assert next(r for r in ranked if r.code == "PART").factors_available == 3


def test_empty_universe_ranks_to_nothing() -> None:
    assert rank_universe([]) == []


# --- construction ---------------------------------------------------------------------------------


def test_sleeve_takes_only_the_target_count() -> None:
    ranked = rank_universe([_scored(f"S{i}", value=i / 100) for i in range(60)])
    weights = sleeve_weights(ranked, SleevePolicy(target_positions=40))
    assert len(weights) == 40


def test_no_position_exceeds_the_cap() -> None:
    ranked = rank_universe([_scored(f"S{i}", value=i / 100, vol=0.05 if i == 0 else 0.6)
                            for i in range(40)])
    weights = sleeve_weights(ranked, SleevePolicy(target_positions=40, max_position_pct=0.03))
    assert max(weights.values()) <= 0.03 + 1e-9


def test_sleeve_never_implies_leverage() -> None:
    ranked = rank_universe([_scored(f"S{i}", value=i / 100, vol=0.1) for i in range(30)])
    weights = sleeve_weights(ranked, SleevePolicy(target_positions=30, max_position_pct=0.10))
    assert sum(weights.values()) <= 1.0 + 1e-9


def test_lower_volatility_earns_more_weight_within_the_bands() -> None:
    ranked = rank_universe([
        _scored("CALM", value=0.6, vol=0.10),
        _scored("WILD", value=0.6, vol=0.80),
    ] + [_scored(f"S{i}", value=0.5, vol=0.3) for i in range(10)])
    weights = sleeve_weights(ranked, SleevePolicy(target_positions=12, max_position_pct=0.10))
    assert weights["CALM"] > weights["WILD"]


def test_unknown_volatility_falls_back_to_equal_weight_not_exclusion() -> None:
    universe = [_scored("NOVOL", vol=None), _scored("HASVOL", vol=0.3)]
    universe += [_scored(f"S{i}", vol=0.3) for i in range(18)]
    weights = sleeve_weights(rank_universe(universe), SleevePolicy(target_positions=20))
    # A name we cannot measure volatility for is weighted at 1/N, neither dropped nor guessed at.
    assert "NOVOL" in weights and weights["NOVOL"] > 0


def test_empty_ranking_builds_no_book() -> None:
    assert sleeve_weights([]) == {}


# --- the nulls (Phase 13.3.4) -----------------------------------------------------------------


def test_equal_weight_null_is_uniform_and_fully_invested() -> None:
    weights = equal_weight_null(["A", "B", "C", "D"])
    assert all(w == pytest.approx(0.25) for w in weights.values())
    assert sum(weights.values()) == pytest.approx(1.0)


def test_single_factor_null_picks_on_one_factor_only() -> None:
    # Six candidates, a five-name book: whoever gets left out reveals which factor was ranked on.
    scores = [
        _scored("MOMWIN", value=0.0, momentum=0.9),
        _scored("MOMLOSE", value=0.9, momentum=-0.5),
    ] + [_scored(f"S{i}", value=0.5, momentum=0.5) for i in range(4)]
    policy = SleevePolicy(target_positions=5)

    on_momentum = single_factor_null(scores, "momentum", policy)
    assert "MOMWIN" in on_momentum and "MOMLOSE" not in on_momentum

    on_value = single_factor_null(scores, "value", policy)
    assert "MOMLOSE" in on_value and "MOMWIN" not in on_value


def test_unknown_factor_is_rejected() -> None:
    with pytest.raises(ValueError):
        single_factor_null([_scored("A")], "sentiment")


def test_nulls_are_empty_when_nothing_qualifies() -> None:
    assert equal_weight_null([]) == {}
    assert single_factor_null([], "value") == {}
