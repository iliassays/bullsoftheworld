"""System A book construction: turning filing signals into a sized, gated paper portfolio.

``filing_signals`` answers *which filing events qualify and when*. This module answers *which of
those we would actually hold, at what weight, and when we would let go* — the book rules from
Phase 12 (System A) with the limits from the Phase 15 rulebook.

The rules, each with its source:

- **Tradeable gate** (15 L1) — a spread ceiling, not a price-action filter. Phase 7's finding is
  that spread, not market impact, is retail's real cost, and it bites hardest in exactly the small
  caps where insider signals are strongest. The two findings collide and the gate is where that
  collision is priced.
- **Crowding screen** (15 L2) — no entry into heavily shorted names. Each position is deliberately
  co-invested with a large holder, so crowding is the one conjunction risk this book cannot cap by
  construction; it is screened at entry instead.
- **Equal weight with a position cap** (12) — 1/N inside the book (DeMiguel: nothing beats it out
  of sample), capped per name at cost, with a hard ceiling on concurrent events.
- **Exits** (12) — a hard time stop at the documented drift horizon, plus immediate exit on a
  thesis break. Trigger *type* sets exit speed (Phase 7 finding 3); a thesis break is never run on
  a valuation timetable.
- **Leverage and shorting are hard zero** (15 L1) — the conjunction-breaker. Not configurable.

**Rejections are first-class.** Phase 13.4 requires event books to log non-events: every screened
candidate carries its rejection reasons, because a disqualification layer that discards silently
is untestable. ``screen_candidates`` therefore returns every candidate, not just the survivors.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, Field

EventKind = Literal["insider_cluster", "activist_13d"]
ExitReason = Literal["time_stop", "thesis_break", "stake_exit", "converted_to_13g"]


class BookPolicy(BaseModel):
    """Entry gates and sizing limits. Ranges are Phase 15 hypotheses, fixed at preregistration."""

    max_position_pct: float = Field(default=0.05, gt=0, le=0.10)
    max_concurrent_positions: int = Field(default=20, ge=1)
    # Tradeable gate: measured half-spread ceiling in bps (cost observatory supplies the input).
    max_half_spread_bps: float = Field(default=100.0, gt=0)
    # Crowding screen: short interest as a percent of float.
    max_short_interest_pct: float = Field(default=20.0, gt=0)
    # The crowding screen needs short-interest-vs-float, a metric we do not yet ingest (we have
    # daily short *volume*, which is not the same thing). Disabling it is an explicit, recorded
    # choice -- the book then runs with one fewer gate, and that limitation must be reported, never
    # hidden. Set True only once a real short-interest feed exists.
    screen_crowding: bool = True
    minimum_market_cap_mn: float = Field(default=50.0, ge=0)
    # Market cap is a *secondary* tradeability gate -- the measured spread is the primary one. When
    # False, a name with no shares-outstanding data is not rejected for that alone (the spread gate
    # still protects us); a name whose cap IS known and below the floor is still rejected. Set True
    # to demand cap data on every name. Coverage of shares-outstanding is ~50%, so requiring it
    # discards good candidates for a data gap rather than a real disqualification.
    require_market_cap: bool = True
    # The documented drift horizon; beyond it the evidence is silent, so the book does not hold.
    time_stop_days: int = Field(default=365, ge=1)

    # Deliberately NOT validated: a policy whose caps leave the book mostly in cash is legitimate,
    # not a misconfiguration. Phase 15 L2 makes cash a valid state with unlimited idle time, and
    # System B's episodic supply is the reason. A book that only ever fires three events should
    # hold three positions and cash, never inflate weights to look busy.


class CandidateEvent(BaseModel):
    """A qualifying signal from ``filing_signals``, normalized for the book."""

    symbol: str
    issuer_cik: int
    kind: EventKind
    signal_at: dt.datetime
    # Ranking input within a crowded signal day. Higher is stronger; comparable within a kind only.
    strength: float = 0.0


class CandidateMarketState(BaseModel):
    """Point-in-time market facts required to screen a candidate. ``None`` means unknown."""

    half_spread_bps: float | None = None
    short_interest_pct_of_float: float | None = None
    market_cap_mn: float | None = None


class ScreenedCandidate(BaseModel):
    """A candidate with its accept/reject verdict and every reason recorded."""

    candidate: CandidateEvent
    accepted: bool
    rejection_reasons: tuple[str, ...] = ()


class BookPosition(BaseModel):
    """An open paper position in the book."""

    symbol: str
    kind: EventKind
    opened_at: dt.datetime
    weight: float


class ExitInstruction(BaseModel):
    symbol: str
    reason: ExitReason
    # Thesis breaks exit immediately and in full; scheduled reasons exit in stages.
    immediate: bool


def screen_candidates(
    candidates: Iterable[CandidateEvent],
    market_state: dict[str, CandidateMarketState],
    policy: BookPolicy,
) -> list[ScreenedCandidate]:
    """Apply the entry gates, recording every rejection reason (Phase 13.4).

    Unknown market data is a rejection, not a pass: a name we cannot price the cost of is a name
    we cannot honestly claim to have traded. Omit over mislead.
    """
    screened: list[ScreenedCandidate] = []
    for candidate in candidates:
        state = market_state.get(candidate.symbol)
        reasons: list[str] = []
        if state is None:
            reasons.append("no_market_state")
        else:
            if state.half_spread_bps is None:
                reasons.append("spread_unknown")
            elif state.half_spread_bps > policy.max_half_spread_bps:
                reasons.append("spread_above_tradeable_gate")

            if policy.screen_crowding:
                if state.short_interest_pct_of_float is None:
                    reasons.append("short_interest_unknown")
                elif state.short_interest_pct_of_float > policy.max_short_interest_pct:
                    reasons.append("crowded_short_interest")

            if state.market_cap_mn is None:
                if policy.require_market_cap:
                    reasons.append("market_cap_unknown")
            elif state.market_cap_mn < policy.minimum_market_cap_mn:
                reasons.append("below_market_cap_floor")
        screened.append(
            ScreenedCandidate(
                candidate=candidate,
                accepted=not reasons,
                rejection_reasons=tuple(reasons),
            )
        )
    return screened


def plan_entries(
    screened: Sequence[ScreenedCandidate],
    open_positions: Sequence[BookPosition],
    policy: BookPolicy,
) -> list[CandidateEvent]:
    """Choose which accepted candidates the book has room for, strongest first.

    Never doubles an existing name: one event per issuer at a time keeps the equal-weight
    construction honest and stops a repeat filer from quietly concentrating the book.
    """
    held = {position.symbol for position in open_positions}
    room = policy.max_concurrent_positions - len(open_positions)
    if room <= 0:
        return []
    eligible = [
        item.candidate
        for item in screened
        if item.accepted and item.candidate.symbol not in held
    ]
    # Deduplicate same-symbol candidates arriving together, keeping the strongest.
    best: dict[str, CandidateEvent] = {}
    for candidate in eligible:
        current = best.get(candidate.symbol)
        if current is None or candidate.strength > current.strength:
            best[candidate.symbol] = candidate
    ordered = sorted(best.values(), key=lambda c: (-c.strength, c.signal_at, c.symbol))
    return ordered[:room]


def target_weights(
    positions: Sequence[BookPosition],
    entries: Sequence[CandidateEvent],
    policy: BookPolicy,
) -> dict[str, float]:
    """Equal-weight the book across held names and new entries, capped per position.

    1/N is the evidence-backed default (DeMiguel — no optimizer beat it out of sample), and the
    per-name cap binds when the book is thin. Weights are gross exposure fractions; leverage is
    structurally impossible here because they can never sum above 1.
    """
    symbols = [position.symbol for position in positions] + [entry.symbol for entry in entries]
    unique = list(dict.fromkeys(symbols))
    if not unique:
        return {}
    equal = 1.0 / len(unique)
    weight = min(equal, policy.max_position_pct)
    return {symbol: round(weight, 6) for symbol in unique}


def exits_due(
    positions: Iterable[BookPosition],
    *,
    as_of: dt.datetime,
    policy: BookPolicy,
    thesis_breaks: dict[str, ExitReason] | None = None,
) -> list[ExitInstruction]:
    """Exits owed as of ``as_of``: thesis breaks immediately, then the hard time stop.

    A thesis break (the activist exits, or a 13D converts to a passive 13G) removes the reason the
    position existed, so it exits in full at once. The time stop is a scheduled, staged exit — the
    documented drift horizon simply ran out, which is not the same event and must not borrow the
    urgency of one.
    """
    breaks = thesis_breaks or {}
    instructions: list[ExitInstruction] = []
    horizon = dt.timedelta(days=policy.time_stop_days)
    for position in positions:
        reason = breaks.get(position.symbol)
        if reason is not None:
            instructions.append(
                ExitInstruction(symbol=position.symbol, reason=reason, immediate=True)
            )
            continue
        if as_of - position.opened_at >= horizon:
            instructions.append(
                ExitInstruction(symbol=position.symbol, reason="time_stop", immediate=False)
            )
    instructions.sort(key=lambda item: item.symbol)
    return instructions


def rejection_summary(screened: Iterable[ScreenedCandidate]) -> dict[str, int]:
    """Tally rejection reasons — the disqualification layer's own testable output."""
    tally: dict[str, int] = {}
    for item in screened:
        for reason in item.rejection_reasons:
            tally[reason] = tally.get(reason, 0) + 1
    return dict(sorted(tally.items(), key=lambda pair: (-pair[1], pair[0])))


class BookState(BaseModel):
    """The book between sessions."""

    positions: list[BookPosition] = Field(default_factory=list)


class BookAdvance(BaseModel):
    """One session's book decisions, with the full audit trail of what was refused."""

    as_of: dt.datetime
    state: BookState
    target_weights: dict[str, float]
    exits: list[ExitInstruction] = Field(default_factory=list)
    entries: list[CandidateEvent] = Field(default_factory=list)
    screened: list[ScreenedCandidate] = Field(default_factory=list)


def advance_book(
    *,
    as_of: dt.datetime,
    state: BookState,
    new_candidates: Sequence[CandidateEvent],
    market_state: dict[str, CandidateMarketState],
    policy: BookPolicy,
    thesis_breaks: dict[str, ExitReason] | None = None,
) -> BookAdvance:
    """Advance the event book by one session: exit first, then screen, then enter.

    Order matters and is deliberate. Exits are resolved *before* entries so a name leaving the book
    frees its slot the same session — otherwise a full book would refuse a fresh signal while
    holding a position it had already decided to close. Nothing here looks at prices: this is the
    book's intent, and execution (next-open fills, costs, ADV limits) is the engine's job.

    Only candidates whose signal is already public as of ``as_of`` are considered; a future-stamped
    event is dropped rather than traded, which is the point-in-time contract enforced at the book
    boundary as well as the signal boundary.
    """
    exits = exits_due(state.positions, as_of=as_of, policy=policy, thesis_breaks=thesis_breaks)
    exiting = {instruction.symbol for instruction in exits}
    surviving = [p for p in state.positions if p.symbol not in exiting]

    knowable = [c for c in new_candidates if c.signal_at <= as_of]
    screened = screen_candidates(knowable, market_state, policy)
    entries = plan_entries(screened, surviving, policy)

    opened = [
        BookPosition(symbol=entry.symbol, kind=entry.kind, opened_at=as_of, weight=0.0)
        for entry in entries
    ]
    positions = surviving + opened
    weights = target_weights(positions, [], policy)
    positions = [p.model_copy(update={"weight": weights.get(p.symbol, 0.0)}) for p in positions]

    return BookAdvance(
        as_of=as_of,
        state=BookState(positions=positions),
        target_weights=weights,
        exits=exits,
        entries=entries,
        screened=screened,
    )


def build_weight_schedule(
    *,
    sessions: Sequence[dt.datetime],
    candidates_by_session: dict[dt.datetime, Sequence[CandidateEvent]],
    market_state_by_session: dict[dt.datetime, dict[str, CandidateMarketState]],
    policy: BookPolicy,
    thesis_breaks_by_session: dict[dt.datetime, dict[str, ExitReason]] | None = None,
) -> tuple[dict[dt.datetime, dict[str, float]], list[BookAdvance]]:
    """Walk the book forward across sessions, returning the target-weight schedule and the trail.

    The schedule is what the execution engine consumes; the advances are the evidence file — every
    entry, exit and refusal, in order. Both are returned because a result without its rejections
    is not reviewable (Phase 13.4).
    """
    breaks = thesis_breaks_by_session or {}
    state = BookState()
    schedule: dict[dt.datetime, dict[str, float]] = {}
    advances: list[BookAdvance] = []
    for session in sorted(sessions):
        advance = advance_book(
            as_of=session,
            state=state,
            new_candidates=candidates_by_session.get(session, ()),
            market_state=market_state_by_session.get(session, {}),
            policy=policy,
            thesis_breaks=breaks.get(session),
        )
        state = advance.state
        schedule[session] = advance.target_weights
        advances.append(advance)
    return schedule, advances
