"""Daily Shortlist — always-full daily research slate for the DSE.

**The problem this fixes.** Scheme-3 (`strategies.py`, the `quality_reversal_eod` book) requires
four boolean gates to align on the same session. Measured over 232 usable DSE sessions
(`research/edge_discovery/scheme3_diagnostic.py`): they align on **21.6%** of sessions, so a
researcher opening the app sees an empty slate **78% of the time**. The `quality_reversal_eod`
paper book has taken zero trades since going live. That is not a bug — requiring a stock to sit
within 15% of its 52-week low *and* break its prior 5-day high is nearly self-contradictory, and
that single gate removes 96% of candidates.

This module always returns ``size`` names, by **ranking** the eligible universe instead of
demanding every gate pass.

**What this ranking is, and is not.** It is an *attention* ranking: where a researcher should
spend the next hour. It is not a prediction, and the code must never be presented as one. That is
not modesty, it is a measurement — from `research/edge_discovery/run_daily_five.py`, over
2024-06 to 2026-07:

* A return-seeking rank (washout depth + range position + turn + cheapness) scored **+1.92%** per
  63 sessions against a random draw from the same pool at **+3.17%**. The ranking was **worse
  than random**, so no ranking here is allowed to claim it picks winners.
* The quality gate did not discriminate either: the pool that *failed* quality returned **+6.62%**
  against the quality pool's +3.17%.
* Everything positive in that window was the market. Splitting it: **-0.51%** (hit 47%) to
  2026-01, then **+12.70%** (hit 91%) to 2026-07. A 91% hit rate means everything rose.
* Scheme-3's strict rule itself returned **-2.14%** on its 78 positions.

So the honest product is a **descriptive evidence surface**: these are liquid, seasoned companies
where something measurable happened today, with the data attached and the exclusions named. That
is genuinely useful — it is how a researcher allocates attention across ~400 codes — and it is
what the platform's descriptive-only rule requires. Ranking by "what changed" also carries a known
*negative* drift (high relative volume measured -169bps in the US program), which is exactly why
the output may never be framed as a buy list.

Pure functions over already-loaded rows: no I/O, no AI, deterministic.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

METHODOLOGY_VERSION = "daily_shortlist_v1"

DEFAULT_SIZE = 5
# Liquidity and seasoning floors. A name below these cannot be researched honestly: the price is
# not a reliable read and the history is too short for any structural statement.
MIN_AVG_VOLUME = 5_000
MIN_BARS = 260
# Above this, the multiple says earnings are negligible rather than saying anything about value,
# so it moves from the reasons list to the cautions list.
EXTREME_PE = 60.0

# Disclosed attention weights. Equal-ish and deliberately few — there is no fitted parameter
# here, because a fitted parameter would imply a return claim the evidence does not support.
W_MOVE = 0.35
W_VOLUME = 0.25
W_LEVEL = 0.25
W_RANGE = 0.15

# Measured base rates, carried in the output so a UI cannot show the slate without them.
BASE_RATES = {
    "window": "2024-06-27..2026-07-23, 232 usable DSE sessions",
    "return_rank_vs_random_pp": -1.24,
    "quality_pool_pct": 3.17,
    "non_quality_pool_pct": 6.62,
    "dsex_same_dates_pct": 1.50,
    "regime_split": {"to_2026_01_pct": -0.51, "from_2026_02_pct": 12.70},
    "scheme3_strict_pct": -2.14,
    "verdict": "No selection rule tested beat a random draw from the same pool. Ranking is "
    "attention allocation, not prediction.",
}


@dataclass(frozen=True, slots=True)
class ShortlistCandidate:
    """One eligible name with today's descriptive facts. Missing values stay None."""

    code: str
    close: float
    avg_volume_20: float | None = None
    bars_seen: int | None = None
    change_pct: float | None = None
    volume: float | None = None
    # Distance to the nearest structural level (52w high/low, SMA-200) as a % of price.
    pct_from_52w_high: float | None = None
    range_position_pct: float | None = None
    sma_200: float | None = None
    eps: float | None = None
    nav_per_share: float | None = None
    pe: float | None = None
    sector: str | None = None


@dataclass(frozen=True, slots=True)
class ShortlistFact:
    """One localisable statement about a row: a ``kind`` plus at most one number.

    Kept structured so a Bangla-first client renders Bangla. See ``render_fact_en``.
    """

    kind: str
    value: float | None = None


@dataclass(frozen=True, slots=True)
class ShortlistEntry:
    """One slate row: the name, why it surfaced, and what we do not know about it."""

    code: str
    rank: int
    attention_score: float
    close: float
    change_pct: float | None
    # Structured, for localisation. ``reasons``/``unknowns`` are the English renderings of these.
    facts: list[ShortlistFact] = field(default_factory=list)
    cautions: list[ShortlistFact] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    sector: str | None = None
    pe: float | None = None


@dataclass(frozen=True, slots=True)
class DailyShortlist:
    """The slate for one session. ``is_return_claim`` is False and is not configurable."""

    market: str
    as_of: dt.date
    size: int
    entries: list[ShortlistEntry]
    eligible_names: int
    excluded_illiquid: int
    excluded_short_history: int
    is_return_claim: bool = False
    methodology_version: str = METHODOLOGY_VERSION
    base_rates: dict = field(default_factory=lambda: dict(BASE_RATES))
    notes: list[str] = field(default_factory=list)


def _percentile_ranks(values: list[float | None]) -> list[float]:
    """Within-slate percentile of each non-None value; None ranks 0.0 (never surfaced for it)."""
    present = sorted(v for v in values if v is not None)
    if not present:
        return [0.0] * len(values)
    span = len(present)
    out = []
    for value in values:
        if value is None:
            out.append(0.0)
            continue
        # Fraction of the pool at or below this value.
        below = sum(1 for other in present if other <= value)
        out.append(below / span)
    return out


def is_eligible(candidate: ShortlistCandidate) -> bool:
    """Liquid and seasoned enough to research. Deliberately the ONLY hard gate.

    Quality (EPS/NAV/PE) is *not* a gate here: measured over 232 sessions the non-quality pool
    outperformed the quality pool, so excluding those names would be an unevidenced editorial
    choice dressed as risk control. Quality facts still ride along on every row so a reader can
    apply their own filter.
    """
    if candidate.close <= 0:
        return False
    if candidate.avg_volume_20 is not None and candidate.avg_volume_20 < MIN_AVG_VOLUME:
        return False
    return not (candidate.bars_seen is not None and candidate.bars_seen < MIN_BARS)


def _relative_volume(candidate: ShortlistCandidate) -> float | None:
    if candidate.volume is None or not candidate.avg_volume_20:
        return None
    return candidate.volume / candidate.avg_volume_20


def _level_proximity(candidate: ShortlistCandidate) -> float | None:
    """How close the close sits to a structural level, as a 0-1 score (1 = touching one)."""
    distances = []
    if candidate.pct_from_52w_high is not None:
        distances.append(abs(candidate.pct_from_52w_high))
    if candidate.range_position_pct is not None:
        distances.append(min(candidate.range_position_pct, 100.0 - candidate.range_position_pct))
    if candidate.sma_200 and candidate.sma_200 > 0:
        distances.append(abs(candidate.close / candidate.sma_200 - 1.0) * 100.0)
    if not distances:
        return None
    nearest = min(distances)
    # 0% away -> 1.0; 20% or more away -> 0.0.
    return max(0.0, 1.0 - nearest / 20.0)


def _facts(candidate: ShortlistCandidate, rel_volume: float | None) -> list[ShortlistFact]:
    """Structured statements of fact. Never a recommendation, never a forecast.

    Structured rather than prose because the first tenant is Bangla-first: rendering English
    sentences here would put English evidence inside a Bangla UI. The client localises each
    ``kind``; ``render_fact_en`` below is the fallback for English tenants and the CLI.
    """
    facts: list[ShortlistFact] = []
    if candidate.change_pct is not None:
        facts.append(ShortlistFact(kind="move", value=candidate.change_pct))
    if rel_volume is not None and rel_volume >= 1.5:
        facts.append(ShortlistFact(kind="rel_volume", value=rel_volume))
    if candidate.pct_from_52w_high is not None and abs(candidate.pct_from_52w_high) <= 3.0:
        facts.append(ShortlistFact(kind="near_52w_high"))
    if candidate.range_position_pct is not None and candidate.range_position_pct <= 15.0:
        facts.append(ShortlistFact(kind="range_bottom"))
    if candidate.sma_200 and candidate.sma_200 > 0:
        gap = (candidate.close / candidate.sma_200 - 1.0) * 100.0
        if abs(gap) <= 2.0:
            facts.append(ShortlistFact(kind="at_sma_200"))
    # Only a sane P/E belongs in the facts list. An extreme multiple is a caution, not a
    # feature, and listing "P/E 820" among the reasons reads as an endorsement to a naive reader.
    if (
        candidate.pe is not None
        and candidate.eps is not None
        and candidate.eps > 0
        and candidate.pe <= EXTREME_PE
    ):
        facts.append(ShortlistFact(kind="pe", value=candidate.pe))
    return facts


def _cautions(candidate: ShortlistCandidate) -> list[ShortlistFact]:
    """What we cannot say. Omit-over-mislead, made explicit per row."""
    gaps: list[ShortlistFact] = []
    if candidate.eps is None or candidate.nav_per_share is None:
        gaps.append(ShortlistFact(kind="no_fundamentals"))
    # Quality is not a gate here (the non-quality pool outperformed over the tested window), so
    # the risk it would have screened out has to be stated on the row instead of silently dropped.
    if candidate.eps is not None and candidate.eps <= 0:
        gaps.append(ShortlistFact(kind="loss_making"))
    if candidate.nav_per_share is not None and candidate.nav_per_share <= 0:
        gaps.append(ShortlistFact(kind="negative_book"))
    if candidate.pe is not None and candidate.pe > EXTREME_PE:
        gaps.append(ShortlistFact(kind="extreme_pe", value=candidate.pe))
    if candidate.sma_200 is None:
        gaps.append(ShortlistFact(kind="no_sma_200"))
    # DSE bars are raw closes; a bonus or rights ex-date presents as a price drop.
    if candidate.change_pct is not None and candidate.change_pct <= -8.0:
        gaps.append(ShortlistFact(kind="possible_corporate_action"))
    return gaps


def render_fact_en(fact: ShortlistFact) -> str:
    """English rendering — the fallback for English tenants, the CLI and tests."""
    value = fact.value
    match fact.kind:
        case "move" if value is not None:
            return f"{'rose' if value >= 0 else 'fell'} {abs(value):.2f}% today"
        case "rel_volume" if value is not None:
            return f"traded {value:.1f}x its 20-day average volume"
        case "near_52w_high":
            return "within 3% of its 52-week high"
        case "range_bottom":
            return "in the bottom 15% of its 52-week range"
        case "at_sma_200":
            return "sitting on its 200-day average"
        case "pe" if value is not None:
            return f"P/E {value:.1f} on last reported annual EPS"
        case "no_fundamentals":
            return "no reported annual EPS/NAV on file"
        case "loss_making":
            return "loss-making on last reported annual EPS"
        case "negative_book":
            return "negative book value per share"
        case "extreme_pe" if value is not None:
            return f"P/E {value:.0f} — earnings are negligible against the price"
        case "no_sma_200":
            return "no 200-day average yet"
        case "possible_corporate_action":
            return "large drop may be a corporate action — DSE closes are unadjusted"
        case _:
            return fact.kind


def build_daily_shortlist(
    candidates: Sequence[ShortlistCandidate],
    *,
    market: str,
    as_of: dt.date,
    size: int = DEFAULT_SIZE,
) -> DailyShortlist:
    """Rank the eligible universe and return the top ``size``. Always full when data exists.

    Returns fewer than ``size`` only when fewer eligible names exist — and says so in ``notes``
    rather than padding the slate with names that failed the liquidity floor.
    """
    illiquid = sum(
        1 for c in candidates if c.avg_volume_20 is not None and c.avg_volume_20 < MIN_AVG_VOLUME
    )
    short_history = sum(1 for c in candidates if c.bars_seen is not None and c.bars_seen < MIN_BARS)
    eligible = [c for c in candidates if is_eligible(c)]

    notes: list[str] = []
    if not eligible:
        notes.append(f"No name met the liquidity and history floors on {as_of}.")
        return DailyShortlist(
            market=market,
            as_of=as_of,
            size=size,
            entries=[],
            eligible_names=0,
            excluded_illiquid=illiquid,
            excluded_short_history=short_history,
            notes=notes,
        )

    rel_volumes = [_relative_volume(c) for c in eligible]
    moves = [abs(c.change_pct) if c.change_pct is not None else None for c in eligible]
    levels = [_level_proximity(c) for c in eligible]
    # Range extremity: distance from mid-range, so both ends of the 52-week range surface.
    ranges = [
        abs(c.range_position_pct - 50.0) if c.range_position_pct is not None else None
        for c in eligible
    ]

    move_r = _percentile_ranks(moves)
    vol_r = _percentile_ranks(rel_volumes)
    level_r = _percentile_ranks(levels)
    range_r = _percentile_ranks(ranges)

    scored = [
        (
            W_MOVE * move_r[i] + W_VOLUME * vol_r[i] + W_LEVEL * level_r[i] + W_RANGE * range_r[i],
            eligible[i],
            rel_volumes[i],
        )
        for i in range(len(eligible))
    ]
    # Deterministic tie-break on code so the same inputs always give the same slate.
    scored.sort(key=lambda item: (-item[0], item[1].code))

    entries = [
        ShortlistEntry(
            code=candidate.code,
            rank=position,
            attention_score=round(score, 4),
            close=candidate.close,
            change_pct=candidate.change_pct,
            facts=(facts := _facts(candidate, rel_volume)),
            cautions=(cautions := _cautions(candidate)),
            reasons=[render_fact_en(fact) for fact in facts],
            unknowns=[render_fact_en(caution) for caution in cautions],
            sector=candidate.sector,
            pe=candidate.pe,
        )
        for position, (score, candidate, rel_volume) in enumerate(scored[:size], start=1)
    ]

    if len(entries) < size:
        notes.append(
            f"Only {len(entries)} of {size} slots filled — {len(eligible)} eligible names on "
            f"{as_of}. The slate is never padded below the liquidity floor."
        )
    notes.append(
        "Attention ranking, not a forecast: over 232 tested sessions no selection rule beat a "
        "random draw from the same pool, and a return-seeking rank did 1.24pp worse."
    )
    return DailyShortlist(
        market=market,
        as_of=as_of,
        size=size,
        entries=entries,
        eligible_names=len(eligible),
        excluded_illiquid=illiquid,
        excluded_short_history=short_history,
        notes=notes,
    )


def with_note(shortlist: DailyShortlist, note: str) -> DailyShortlist:
    """Append a caller-supplied note (for example a market-regime caveat)."""
    return replace(shortlist, notes=[*shortlist.notes, note])
