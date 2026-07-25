from __future__ import annotations

import datetime as dt
import re

from bulls.analytics.daily_shortlist import (
    MIN_AVG_VOLUME,
    MIN_BARS,
    ShortlistCandidate,
    build_daily_shortlist,
    is_eligible,
)

AS_OF = dt.date(2026, 7, 23)


def candidate(code: str, **kwargs) -> ShortlistCandidate:
    """An eligible, unremarkable name by default; each test perturbs one field."""
    base = {
        "close": 100.0,
        "avg_volume_20": 50_000.0,
        "bars_seen": 400,
        "change_pct": 0.5,
        "volume": 50_000.0,
        "pct_from_52w_high": -25.0,
        "range_position_pct": 50.0,
        "sma_200": 120.0,
        "eps": 5.0,
        "nav_per_share": 40.0,
        "pe": 20.0,
    }
    return ShortlistCandidate(code=code, **{**base, **kwargs})


def test_slate_is_always_full_when_enough_names_exist() -> None:
    """The whole point: Scheme-3 left the slate empty 78% of sessions. Ranking never does."""
    pool = [candidate(f"C{i}", change_pct=float(i)) for i in range(40)]

    result = build_daily_shortlist(pool, market="DSE", as_of=AS_OF, size=5)

    assert len(result.entries) == 5
    assert [e.rank for e in result.entries] == [1, 2, 3, 4, 5]
    assert result.eligible_names == 40


def test_liquidity_and_history_are_the_only_hard_gates() -> None:
    assert is_eligible(candidate("OK"))
    assert not is_eligible(candidate("THIN", avg_volume_20=MIN_AVG_VOLUME - 1))
    assert not is_eligible(candidate("NEW", bars_seen=MIN_BARS - 1))
    assert not is_eligible(candidate("ZERO", close=0.0))
    # Quality is NOT a gate — the non-quality pool outperformed over the tested window.
    assert is_eligible(candidate("LOSS", eps=-2.0, nav_per_share=-5.0, pe=None))


def test_exclusions_are_counted_not_hidden() -> None:
    pool = [
        candidate("GOOD"),
        candidate("THIN", avg_volume_20=100.0),
        candidate("NEW", bars_seen=10),
    ]

    result = build_daily_shortlist(pool, market="DSE", as_of=AS_OF, size=5)

    assert [e.code for e in result.entries] == ["GOOD"]
    assert result.excluded_illiquid == 1
    assert result.excluded_short_history == 1
    # A short slate says so rather than padding below the floor.
    assert any("Only 1 of 5" in note for note in result.notes)


def test_empty_universe_returns_empty_slate_with_a_reason() -> None:
    result = build_daily_shortlist(
        [candidate("THIN", avg_volume_20=1.0)], market="DSE", as_of=AS_OF, size=5
    )

    assert result.entries == []
    assert result.eligible_names == 0
    assert any("liquidity and history floors" in note for note in result.notes)


def test_bigger_move_and_volume_spike_outrank_a_quiet_name() -> None:
    pool = [
        candidate("QUIET", change_pct=0.1, volume=50_000.0),
        candidate("ACTIVE", change_pct=9.0, volume=250_000.0),
    ]

    result = build_daily_shortlist(pool, market="DSE", as_of=AS_OF, size=2)

    assert result.entries[0].code == "ACTIVE"
    assert result.entries[0].attention_score > result.entries[1].attention_score


def test_ranking_is_deterministic_under_ties() -> None:
    pool = [candidate("BBB"), candidate("AAA"), candidate("CCC")]

    first = build_daily_shortlist(pool, market="DSE", as_of=AS_OF, size=3)
    second = build_daily_shortlist(list(reversed(pool)), market="DSE", as_of=AS_OF, size=3)

    assert [e.code for e in first.entries] == [e.code for e in second.entries]
    assert [e.code for e in first.entries] == ["AAA", "BBB", "CCC"]


def test_reasons_are_facts_and_unknowns_are_stated() -> None:
    entry = build_daily_shortlist(
        [candidate("X", change_pct=4.2, volume=150_000.0, range_position_pct=8.0, pe=12.0)],
        market="DSE",
        as_of=AS_OF,
        size=1,
    ).entries[0]

    text = " ".join(entry.reasons)
    assert "rose 4.20% today" in text
    assert "3.0x its 20-day average volume" in text
    assert "bottom 15% of its 52-week range" in text
    assert "P/E 12.0" in text


def test_missing_fundamentals_surface_as_unknowns_not_silence() -> None:
    entry = build_daily_shortlist(
        [candidate("X", eps=None, nav_per_share=None, sma_200=None)],
        market="DSE",
        as_of=AS_OF,
        size=1,
    ).entries[0]

    assert any("no reported annual EPS/NAV" in u for u in entry.unknowns)
    assert any("no 200-day average" in u for u in entry.unknowns)


def test_extreme_pe_is_a_caution_not_a_reason() -> None:
    """A real slate ranked MLDYEING at P/E 820. In a reasons list that reads as an endorsement."""
    entry = build_daily_shortlist(
        [candidate("X", eps=0.02, pe=820.0)], market="DSE", as_of=AS_OF, size=1
    ).entries[0]

    assert not any("P/E" in r for r in entry.reasons)
    assert any("earnings are negligible" in u for u in entry.unknowns)


def test_loss_making_and_negative_book_are_stated_on_the_row() -> None:
    """Quality is not a gate, so the risk it would have screened must be visible instead."""
    entry = build_daily_shortlist(
        [candidate("X", eps=-3.0, nav_per_share=-8.0, pe=None)],
        market="DSE",
        as_of=AS_OF,
        size=1,
    ).entries[0]

    assert any("loss-making" in u for u in entry.unknowns)
    assert any("negative book value" in u for u in entry.unknowns)


def test_large_drop_warns_about_unadjusted_dse_closes() -> None:
    """DSE closes are raw: a bonus/rights ex-date looks like a crash. Never present it as one."""
    entry = build_daily_shortlist(
        [candidate("X", change_pct=-12.0)], market="DSE", as_of=AS_OF, size=1
    ).entries[0]

    assert any("corporate action" in u for u in entry.unknowns)


def test_output_can_never_claim_a_return() -> None:
    result = build_daily_shortlist([candidate("X")], market="DSE", as_of=AS_OF, size=1)

    assert result.is_return_claim is False
    # The measured base rates ride along so a UI cannot render the slate without them.
    assert result.base_rates["return_rank_vs_random_pp"] == -1.24
    assert "random draw" in " ".join(result.notes)

    text = " ".join(result.notes + [r for e in result.entries for r in e.reasons]).lower()
    for banned in ("buy", "sell", "hold", "target", "should", "recommend", "undervalued", "will"):
        assert not re.search(rf"\b{banned}\b", text), f"advice word {banned!r} in {text!r}"
