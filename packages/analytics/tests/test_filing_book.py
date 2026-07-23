"""Tests for System A book construction (Phase 12 book rules + Phase 15 limits)."""

from __future__ import annotations

import datetime as dt

import pytest

from bulls.analytics.filing_book import (
    BookPolicy,
    BookPosition,
    BookState,
    CandidateEvent,
    CandidateMarketState,
    advance_book,
    build_weight_schedule,
    exits_due,
    plan_entries,
    rejection_summary,
    screen_candidates,
    target_weights,
)

_NOW = dt.datetime(2026, 3, 2, 21, tzinfo=dt.UTC)
_POLICY = BookPolicy()


def _candidate(symbol: str, *, strength: float = 1.0, kind="insider_cluster") -> CandidateEvent:
    return CandidateEvent(
        symbol=symbol, issuer_cik=abs(hash(symbol)) % 10**6, kind=kind,
        signal_at=_NOW, strength=strength,
    )


def _good_state(**overrides) -> CandidateMarketState:
    base = {"half_spread_bps": 20.0, "short_interest_pct_of_float": 5.0, "market_cap_mn": 500.0}
    base.update(overrides)
    return CandidateMarketState(**base)


# --- entry gates ---------------------------------------------------------------------------


def test_clean_candidate_is_accepted() -> None:
    result = screen_candidates([_candidate("AAA")], {"AAA": _good_state()}, _POLICY)[0]
    assert result.accepted is True
    assert result.rejection_reasons == ()


def test_wide_spread_is_rejected_by_the_tradeable_gate() -> None:
    state = {"AAA": _good_state(half_spread_bps=250.0)}
    result = screen_candidates([_candidate("AAA")], state, _POLICY)[0]
    assert result.accepted is False
    assert "spread_above_tradeable_gate" in result.rejection_reasons


def test_crowded_short_interest_is_rejected() -> None:
    state = {"AAA": _good_state(short_interest_pct_of_float=35.0)}
    result = screen_candidates([_candidate("AAA")], state, _POLICY)[0]
    assert "crowded_short_interest" in result.rejection_reasons


def test_below_market_cap_floor_is_rejected() -> None:
    state = {"AAA": _good_state(market_cap_mn=5.0)}
    result = screen_candidates([_candidate("AAA")], state, _POLICY)[0]
    assert "below_market_cap_floor" in result.rejection_reasons


def test_unknown_market_data_is_a_rejection_not_a_pass() -> None:
    # Omit over mislead: a name whose cost we cannot price is not a name we can claim to trade.
    state = {"AAA": _good_state(half_spread_bps=None, short_interest_pct_of_float=None)}
    result = screen_candidates([_candidate("AAA")], state, _POLICY)[0]
    assert result.accepted is False
    assert "spread_unknown" in result.rejection_reasons
    assert "short_interest_unknown" in result.rejection_reasons


def test_missing_market_state_entirely_is_rejected() -> None:
    result = screen_candidates([_candidate("AAA")], {}, _POLICY)[0]
    assert result.rejection_reasons == ("no_market_state",)


def test_every_candidate_is_returned_so_rejections_stay_auditable() -> None:
    # Phase 13.4: the disqualification layer is only testable if its rejections are recorded.
    candidates = [_candidate("AAA"), _candidate("BBB"), _candidate("CCC")]
    state = {
        "AAA": _good_state(),
        "BBB": _good_state(half_spread_bps=400.0),
        "CCC": _good_state(short_interest_pct_of_float=99.0),
    }
    screened = screen_candidates(candidates, state, _POLICY)
    assert len(screened) == 3
    assert rejection_summary(screened) == {
        "crowded_short_interest": 1,
        "spread_above_tradeable_gate": 1,
    }


# --- entry planning ------------------------------------------------------------------------


def test_book_respects_the_concurrency_cap() -> None:
    policy = BookPolicy(max_concurrent_positions=3)
    held = [
        BookPosition(symbol="H1", kind="activist_13d", opened_at=_NOW, weight=0.05),
        BookPosition(symbol="H2", kind="activist_13d", opened_at=_NOW, weight=0.05),
    ]
    candidates = [_candidate(s) for s in ("AAA", "BBB", "CCC")]
    state = {s: _good_state() for s in ("AAA", "BBB", "CCC")}
    entries = plan_entries(screen_candidates(candidates, state, policy), held, policy)
    assert len(entries) == 1  # only one slot left


def test_full_book_takes_nothing() -> None:
    policy = BookPolicy(max_concurrent_positions=1)
    held = [BookPosition(symbol="H1", kind="activist_13d", opened_at=_NOW, weight=0.05)]
    screened = screen_candidates([_candidate("AAA")], {"AAA": _good_state()}, policy)
    assert plan_entries(screened, held, policy) == []


def test_existing_holdings_are_never_doubled() -> None:
    held = [BookPosition(symbol="AAA", kind="insider_cluster", opened_at=_NOW, weight=0.05)]
    screened = screen_candidates([_candidate("AAA")], {"AAA": _good_state()}, _POLICY)
    assert plan_entries(screened, held, _POLICY) == []


def test_strongest_candidates_are_taken_first() -> None:
    policy = BookPolicy(max_concurrent_positions=2)
    candidates = [_candidate("LOW", strength=0.1), _candidate("HIGH", strength=9.0),
                  _candidate("MID", strength=5.0)]
    state = {s: _good_state() for s in ("LOW", "HIGH", "MID")}
    entries = plan_entries(screen_candidates(candidates, state, policy), [], policy)
    assert [e.symbol for e in entries] == ["HIGH", "MID"]


def test_duplicate_symbol_candidates_collapse_to_the_strongest() -> None:
    candidates = [_candidate("AAA", strength=1.0), _candidate("AAA", strength=7.0)]
    entries = plan_entries(screen_candidates(candidates, {"AAA": _good_state()}, _POLICY), [], _POLICY)
    assert len(entries) == 1
    assert entries[0].strength == 7.0


def test_rejected_candidates_never_enter() -> None:
    screened = screen_candidates([_candidate("BAD")], {"BAD": _good_state(market_cap_mn=1.0)}, _POLICY)
    assert plan_entries(screened, [], _POLICY) == []


# --- sizing --------------------------------------------------------------------------------


def test_equal_weight_binds_when_the_book_is_full() -> None:
    # 25 names -> 1/25 = 4% each, below the 5% cap, so equal weighting is what actually binds.
    entries = [_candidate(f"S{i}") for i in range(25)]
    weights = target_weights([], entries, BookPolicy(max_concurrent_positions=25))
    assert len(weights) == 25
    assert all(w == pytest.approx(0.04) for w in weights.values())
    assert sum(weights.values()) == pytest.approx(1.0)


def test_thin_book_stays_capped_and_mostly_in_cash() -> None:
    # 4 names would be 25% each under pure 1/N; the position cap binds instead and the book sits
    # 20% invested, 80% cash. Cash is a valid state (Phase 15 L2), not a failure to deploy.
    weights = target_weights([], [_candidate(s) for s in ("A", "B", "C", "D")], _POLICY)
    assert len(weights) == 4
    assert all(w == pytest.approx(0.05) for w in weights.values())
    assert sum(weights.values()) == pytest.approx(0.20)


def test_position_cap_binds_on_a_thin_book() -> None:
    # Two names would be 50% each; the 5% cap binds instead.
    weights = target_weights([], [_candidate("A"), _candidate("B")], _POLICY)
    assert all(w == pytest.approx(0.05) for w in weights.values())


def test_weights_can_never_imply_leverage() -> None:
    entries = [_candidate(f"S{i}") for i in range(40)]
    weights = target_weights([], entries, BookPolicy(max_concurrent_positions=40))
    assert sum(weights.values()) <= 1.0 + 1e-9


def test_empty_book_has_no_weights() -> None:
    assert target_weights([], [], _POLICY) == {}


# --- exits ---------------------------------------------------------------------------------


def test_time_stop_fires_at_the_drift_horizon_and_is_staged() -> None:
    opened = _NOW - dt.timedelta(days=365)
    position = BookPosition(symbol="AAA", kind="activist_13d", opened_at=opened, weight=0.05)
    exits = exits_due([position], as_of=_NOW, policy=_POLICY)
    assert len(exits) == 1
    assert exits[0].reason == "time_stop"
    # A time stop is a schedule running out, not an emergency — it must not borrow that urgency.
    assert exits[0].immediate is False


def test_position_inside_the_horizon_is_held() -> None:
    opened = _NOW - dt.timedelta(days=200)
    position = BookPosition(symbol="AAA", kind="activist_13d", opened_at=opened, weight=0.05)
    assert exits_due([position], as_of=_NOW, policy=_POLICY) == []


def test_thesis_break_exits_immediately_and_outranks_the_time_stop() -> None:
    opened = _NOW - dt.timedelta(days=400)  # also past the time stop
    position = BookPosition(symbol="AAA", kind="activist_13d", opened_at=opened, weight=0.05)
    exits = exits_due(
        [position], as_of=_NOW, policy=_POLICY, thesis_breaks={"AAA": "converted_to_13g"}
    )
    assert len(exits) == 1
    assert exits[0].reason == "converted_to_13g"
    assert exits[0].immediate is True


def test_stake_exit_is_a_thesis_break() -> None:
    position = BookPosition(symbol="AAA", kind="activist_13d", opened_at=_NOW, weight=0.05)
    exits = exits_due([position], as_of=_NOW, policy=_POLICY, thesis_breaks={"AAA": "stake_exit"})
    assert exits[0].immediate is True


# --- policy validation ---------------------------------------------------------------------


def test_leverage_is_structurally_impossible_via_position_cap_bound() -> None:
    with pytest.raises(ValueError):
        BookPolicy(max_position_pct=0.5)  # above the 10% hard ceiling


def test_cash_heavy_policy_is_legitimate_not_rejected() -> None:
    # A book that can only ever be 15% invested is a valid preregistered choice.
    policy = BookPolicy(max_position_pct=0.05, max_concurrent_positions=3)
    assert policy.max_concurrent_positions == 3


# --- walking the book forward ---------------------------------------------------------------


def _sessions(n: int) -> list[dt.datetime]:
    return [_NOW + dt.timedelta(days=i) for i in range(n)]


def test_advance_opens_a_position_and_weights_it() -> None:
    advance = advance_book(
        as_of=_NOW,
        state=BookState(),
        new_candidates=[_candidate("AAA")],
        market_state={"AAA": _good_state()},
        policy=_POLICY,
    )
    assert [p.symbol for p in advance.state.positions] == ["AAA"]
    assert advance.target_weights == {"AAA": pytest.approx(0.05)}
    assert advance.state.positions[0].weight == pytest.approx(0.05)


def test_advance_ignores_signals_not_yet_public() -> None:
    # A future-stamped event must not be traded: the point-in-time contract holds at the book
    # boundary too, not only inside the signal layer.
    future = _candidate("AAA")
    future = future.model_copy(update={"signal_at": _NOW + dt.timedelta(days=5)})
    advance = advance_book(
        as_of=_NOW, state=BookState(), new_candidates=[future],
        market_state={"AAA": _good_state()}, policy=_POLICY,
    )
    assert advance.state.positions == []
    assert advance.entries == []


def test_exit_frees_its_slot_in_the_same_session() -> None:
    # A full book must not refuse a fresh signal while holding a name it already decided to close.
    policy = BookPolicy(max_concurrent_positions=1)
    held = BookState(
        positions=[BookPosition(symbol="OLD", kind="activist_13d", opened_at=_NOW, weight=0.05)]
    )
    advance = advance_book(
        as_of=_NOW,
        state=held,
        new_candidates=[_candidate("NEW")],
        market_state={"NEW": _good_state()},
        policy=policy,
        thesis_breaks={"OLD": "stake_exit"},
    )
    assert [i.symbol for i in advance.exits] == ["OLD"]
    assert [p.symbol for p in advance.state.positions] == ["NEW"]


def test_schedule_holds_a_position_until_its_time_stop() -> None:
    policy = BookPolicy(time_stop_days=3)
    sessions = _sessions(6)
    schedule, advances = build_weight_schedule(
        sessions=sessions,
        candidates_by_session={sessions[0]: [_candidate("AAA")]},
        market_state_by_session={sessions[0]: {"AAA": _good_state()}},
        policy=policy,
    )
    # Held from entry through to the time stop, then gone.
    assert "AAA" in schedule[sessions[0]]
    assert "AAA" in schedule[sessions[2]]
    assert schedule[sessions[3]] == {}
    assert any(e.reason == "time_stop" for a in advances for e in a.exits)


def test_schedule_records_rejections_across_the_whole_run() -> None:
    sessions = _sessions(2)
    _, advances = build_weight_schedule(
        sessions=sessions,
        candidates_by_session={
            sessions[0]: [_candidate("WIDE")],
            sessions[1]: [_candidate("CROWDED")],
        },
        market_state_by_session={
            sessions[0]: {"WIDE": _good_state(half_spread_bps=900.0)},
            sessions[1]: {"CROWDED": _good_state(short_interest_pct_of_float=80.0)},
        },
        policy=_POLICY,
    )
    all_screened = [s for a in advances for s in a.screened]
    assert rejection_summary(all_screened) == {
        "crowded_short_interest": 1,
        "spread_above_tradeable_gate": 1,
    }
    # Nothing was ever held.
    assert all(a.target_weights == {} for a in advances)


def test_empty_run_produces_an_empty_schedule_not_an_error() -> None:
    sessions = _sessions(3)
    schedule, advances = build_weight_schedule(
        sessions=sessions, candidates_by_session={}, market_state_by_session={}, policy=_POLICY,
    )
    assert all(weights == {} for weights in schedule.values())
    assert len(advances) == 3


def test_crowding_screen_can_be_disabled_without_rejecting_unknown_si() -> None:
    # With no short-interest feed, disabling the screen must let a name through on its other gates
    # rather than rejecting it as "short_interest_unknown".
    policy = BookPolicy(screen_crowding=False)
    state = {"AAA": CandidateMarketState(
        half_spread_bps=20.0, short_interest_pct_of_float=None, market_cap_mn=500.0
    )}
    result = screen_candidates([_candidate("AAA")], state, policy)[0]
    assert result.accepted is True
    assert "short_interest_unknown" not in result.rejection_reasons


def test_crowding_screen_still_fires_when_enabled() -> None:
    policy = BookPolicy(screen_crowding=True)
    state = {"AAA": CandidateMarketState(
        half_spread_bps=20.0, short_interest_pct_of_float=None, market_cap_mn=500.0
    )}
    assert "short_interest_unknown" in screen_candidates([_candidate("AAA")], state, policy)[0].rejection_reasons


def test_market_cap_can_be_a_secondary_gate() -> None:
    # require_market_cap=False: unknown cap passes on the spread gate, but a KNOWN sub-floor cap
    # still rejects. The measured spread is the primary tradeability test.
    policy = BookPolicy(require_market_cap=False)
    unknown = CandidateMarketState(half_spread_bps=20.0, short_interest_pct_of_float=3.0, market_cap_mn=None)
    tiny = CandidateMarketState(half_spread_bps=20.0, short_interest_pct_of_float=3.0, market_cap_mn=5.0)
    results = {r.candidate.symbol: r for r in screen_candidates(
        [_candidate("UNKNOWN"), _candidate("TINY")],
        {"UNKNOWN": unknown, "TINY": tiny}, policy)}
    assert results["UNKNOWN"].accepted is True
    assert "market_cap_unknown" not in results["UNKNOWN"].rejection_reasons
    assert "below_market_cap_floor" in results["TINY"].rejection_reasons


def test_market_cap_required_by_default() -> None:
    state = {"AAA": CandidateMarketState(half_spread_bps=20.0, short_interest_pct_of_float=3.0, market_cap_mn=None)}
    assert "market_cap_unknown" in screen_candidates([_candidate("AAA")], state, BookPolicy())[0].rejection_reasons
