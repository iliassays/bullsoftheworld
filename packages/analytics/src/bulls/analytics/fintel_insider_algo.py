"""Fintel-style insider algo — opportunistic insider cluster buying.

Named for Fintel because that is where the *idea* was scouted (2026-07-25 competitor review);
the implementation and every threshold below are ours, and unlike Fintel's proprietary scores
the weights here are published constants you can audit and change.

**The mechanism.** Cohen, Malloy & Pomorski (*Decoding Inside Information*, JF 2012) showed the
insider-trading signal lives entirely in *opportunistic* trades: insiders who buy on a
predictable calendar schedule carry **zero** predictive power, while insiders trading off
schedule produced roughly 82bps/month. Cluster buys — several insiders inside one window —
have historically run about double the excess return of a lone buyer. So this module is mostly
a set of *exclusions*: the value comes from what it throws away.

Four filters, in order of how much they remove:

1. **Open-market purchases only** (Form 4 code ``P``, acquired). Grants, option exercises and
   tax withholding are compensation events, not opinions.
2. **Rule 10b5-1 plan trades dropped**, using the checkbox the 2022-23 amendments added. A
   scheduled purchase is routine by disclosure — no inference needed.
3. **Calendar-routine insiders dropped** (the CMP rule): an owner who bought in the same
   calendar month in ``min_consecutive_years`` consecutive years is on a program.
4. **Officers and directors count; 10% owners do not** by default. The published effect is an
   officer/director effect; large holders are frequently funds rebalancing.

**Two honesty constraints that shape the code.**

*Eligibility is gated on ``known_at``, never ``transaction_date``.* Form 4 is due two business
days after the trade, so selecting on the transaction date back-dates a signal into a window
where nobody could have acted on it. Published work also finds much of this alpha decays before
the filing is visible, which makes the distinction the whole ballgame rather than a detail.

*The score is not calibrated to returns.* It is a disclosed-weight summary of how much evidence
is present, not an expected return. Per the Atlas mandate this module is a descriptive evidence
surface, not a strategy and not a paper book. "Three officers bought open-market outside a plan"
is a fact; what happens next is not.

**Tested 2026-07-25. The filters did not validate. Read this before building on the score.**
Family I of the edge-discovery program (``research/edge_discovery/``, four specs frozen before
the data was pulled) ran these exact rules over 107,705 point-in-time US Form 4 purchases,
2021-07 to 2026-07:

* **The cluster premium is absent.** A single qualifying buyer scored *better* out of sample than
  a multi-buyer cluster (+75.0 vs -39.7bps holdout; +167.3 vs +157.5bps on filter-operative
  data). ``band`` and the breadth weight therefore rank by evidence *volume*, not by any measured
  return difference — the literature's ~2x cluster premium does not reproduce here.
* **The exclusions did not discriminate.** 10b5-1 scheduled purchases (+471.7bps) and
  calendar-routine purchases (+119.9bps) — both registered as nulls that must come back ~zero —
  were as positive as the opportunistic set. Their confidence intervals are enormous, so the
  honest reading is that five years of Form 4 cannot separate these four groups at all.
* **The 10b5-1 checkbox is empty before 2023** (0 of 39,483 filings in 2021-22). Any historical
  study spanning that boundary silently mixes plan trades into the opportunistic set.

So: the exclusions here are *mechanistically* justified and cheap, and they make the output
honest and readable. They are not measured alpha, and the score must never be ranked, charted, or
described as if it were. ``docs/research/atlas-insider-cluster-study-2026-07-25.md`` is the
report; ``us_insider_cluster_buy`` is ``rejected`` in the edge registry.

Pure functions over already-loaded rows — no I/O, no AI, deterministic.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

METHODOLOGY_VERSION = "fintel_insider_algo_v1"

# Form 4 transaction code for an open-market or private purchase, paired with acquired ("A").
OPEN_MARKET_PURCHASE_CODE = "P"
ACQUIRED = "A"

DEFAULT_WINDOW_DAYS = 90
DEFAULT_MIN_CONSECUTIVE_YEARS = 3

# Score weights. Published deliberately: an undisclosed weighting is the specific thing that
# makes a vendor squeeze score unfalsifiable. Breadth dominates because breadth is the part with
# replicated support; size earns the least because a large buy by one insider is still one
# opinion. Maximum attainable total is 100.
BREADTH_WEIGHT = 40
ROLE_WEIGHT = 20
CONVICTION_WEIGHT = 20
SIZE_WEIGHT = 20

_BREADTH_BASE = 10
_BREADTH_STEP = 12
_OFFICER_POINTS = 12
_DIRECTOR_POINTS = 8
# Stake increase (% of the insider's reported post-trade holding) that earns full conviction.
_CONVICTION_SATURATION_PCT = 50.0
# Aggregate disclosed USD value bands. Bands, not a continuous curve — the underlying evidence
# does not support pretending a $1.1m cluster is measurably better than a $1.0m one.
_SIZE_BANDS: tuple[tuple[float, int], ...] = (
    (5_000_000.0, 20),
    (1_000_000.0, 15),
    (250_000.0, 10),
    (50_000.0, 5),
)

BANDS = ("no_signal", "single_buyer", "cluster", "strong_cluster")


@dataclass(frozen=True, slots=True)
class InsiderTrade:
    """One parsed non-derivative Form 4 row, stamped with when it became public.

    ``known_at`` is EDGAR's acceptance timestamp (falling back to our capture time). It is the
    only field eligibility may be selected on. ``transaction_date`` is ``None`` for rows whose
    filed date was a typo — see the repair migration; such rows are counted, never guessed at.
    """

    owner_cik: int
    known_at: dt.datetime
    transaction_date: dt.date | None = None
    owner_name: str | None = None
    officer_title: str | None = None
    code: str | None = None
    acquired_disposed: str | None = None
    shares: float | None = None
    price_per_share: float | None = None
    shares_owned_after: float | None = None
    is_officer: bool = False
    is_director: bool = False
    is_ten_percent_owner: bool = False
    is_10b5_1_plan: bool = False


@dataclass(frozen=True, slots=True)
class FintelInsiderRead:
    """Descriptive read for one issuer as of one date. Never an instruction."""

    as_of: dt.date
    window_days: int
    band: str
    score: int
    # Distinct owners whose purchases survived every filter — the headline count.
    qualifying_buyers: int
    officer_buyers: int
    director_buyers: int
    purchases: int
    first_purchase_on: dt.date | None
    last_purchase_on: dt.date | None
    aggregate_value_usd: float | None
    # True when at least one surviving purchase disclosed no price, so the value is a floor.
    value_is_partial: bool
    median_stake_increase_pct: float | None
    # Exclusion counts. These are the product: they let a reader see what was discarded and why.
    excluded_plan_rows: int
    excluded_routine_buyers: int
    excluded_ten_percent_buyers: int
    excluded_undated_rows: int
    thin_history_buyers: int
    known_through: dt.datetime | None
    methodology_version: str = METHODOLOGY_VERSION
    evidence: list[str] = field(default_factory=list)


def is_open_market_purchase(trade: InsiderTrade) -> bool:
    """Code ``P`` acquisition of a positive share count. Grants and exercises are not opinions."""
    return (
        trade.code == OPEN_MARKET_PURCHASE_CODE
        and trade.acquired_disposed == ACQUIRED
        and trade.shares is not None
        and trade.shares > 0
    )


def _has_consecutive_run(years: set[int], length: int) -> bool:
    return any(all(year + offset in years for offset in range(length)) for year in years)


def routine_owner_ciks(
    trades: Sequence[InsiderTrade],
    *,
    as_of: dt.date,
    min_consecutive_years: int = DEFAULT_MIN_CONSECUTIVE_YEARS,
) -> frozenset[int]:
    """Owners buying on a calendar program, by the Cohen-Malloy-Pomorski rule.

    Routine means: a purchase in the same calendar month in ``min_consecutive_years``
    consecutive years. Classification reads *purchases only* — a narrowing of CMP, who classify
    on trading generally — because a routine sale programme says nothing about whether a
    purchase is informed.

    Uses the full history available before ``as_of``, not just the signal window; three years of
    pattern cannot be seen through a 90-day lens.
    """

    cutoff = dt.datetime.combine(as_of, dt.time.max, tzinfo=dt.UTC)
    months: dict[int, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
    for trade in trades:
        if trade.known_at > cutoff or trade.transaction_date is None:
            continue
        if not is_open_market_purchase(trade):
            continue
        months[trade.owner_cik][trade.transaction_date.month].add(trade.transaction_date.year)

    routine = {
        owner
        for owner, by_month in months.items()
        if any(_has_consecutive_run(years, min_consecutive_years) for years in by_month.values())
    }
    return frozenset(routine)


def _purchase_years(trades: Sequence[InsiderTrade], owner_cik: int, cutoff: dt.datetime) -> int:
    return len(
        {
            trade.transaction_date.year
            for trade in trades
            if trade.owner_cik == owner_cik
            and trade.transaction_date is not None
            and trade.known_at <= cutoff
            and is_open_market_purchase(trade)
        }
    )


def _breadth_points(buyers: int) -> int:
    if buyers <= 0:
        return 0
    return min(BREADTH_WEIGHT, _BREADTH_BASE + _BREADTH_STEP * (buyers - 1))


def _role_points(officers: int, directors: int) -> int:
    points = (_OFFICER_POINTS if officers else 0) + (_DIRECTOR_POINTS if directors else 0)
    return min(ROLE_WEIGHT, points)


def _conviction_points(median_stake_increase_pct: float | None) -> int:
    if median_stake_increase_pct is None or median_stake_increase_pct <= 0:
        return 0
    ratio = min(1.0, median_stake_increase_pct / _CONVICTION_SATURATION_PCT)
    return round(ratio * CONVICTION_WEIGHT)


def _size_points(aggregate_value_usd: float | None) -> int:
    if aggregate_value_usd is None:
        return 0
    for threshold, points in _SIZE_BANDS:
        if aggregate_value_usd >= threshold:
            return points
    return 0


def _band(qualifying_buyers: int) -> str:
    if qualifying_buyers <= 0:
        return "no_signal"
    if qualifying_buyers == 1:
        return "single_buyer"
    if qualifying_buyers == 2:
        return "cluster"
    return "strong_cluster"


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def evaluate_fintel_insider_algo(
    trades: Sequence[InsiderTrade],
    *,
    as_of: dt.date,
    window_days: int = DEFAULT_WINDOW_DAYS,
    min_consecutive_years: int = DEFAULT_MIN_CONSECUTIVE_YEARS,
    include_ten_percent_owners: bool = False,
    include_thin_history: bool = True,
) -> FintelInsiderRead | None:
    """Evaluate one issuer's insider purchases as of ``as_of``.

    ``trades`` should be the issuer's *full* available history, not the window — the routine
    classifier needs the years behind it. Returns ``None`` only when no row was public by
    ``as_of`` at all; an evaluated issuer with nothing to show returns a ``no_signal`` read, so
    "we looked and found nothing" stays distinguishable from "we had no data".

    ``include_thin_history`` decides owners with fewer than ``min_consecutive_years`` distinct
    purchase years, who can be shown no routine pattern but also cannot be cleared of one. CMP
    drop them; the default here keeps them — a first-ever purchase by a CEO is the classic
    informed buy, and absence of a pattern is what the data can actually show — and reports them
    in ``thin_history_buyers`` so a reader can discount accordingly.
    """

    cutoff = dt.datetime.combine(as_of, dt.time.max, tzinfo=dt.UTC)
    public = [trade for trade in trades if trade.known_at <= cutoff]
    if not public:
        return None

    known_through = max(trade.known_at for trade in public)
    routine = routine_owner_ciks(public, as_of=as_of, min_consecutive_years=min_consecutive_years)
    window_start = as_of - dt.timedelta(days=window_days)

    excluded_plan_rows = 0
    excluded_undated_rows = 0
    excluded_routine: set[int] = set()
    excluded_ten_percent: set[int] = set()
    thin_history: set[int] = set()
    by_owner: dict[int, list[InsiderTrade]] = defaultdict(list)

    for trade in public:
        if not is_open_market_purchase(trade):
            continue
        if trade.is_10b5_1_plan:
            excluded_plan_rows += 1
            continue
        if trade.transaction_date is None:
            # The repair migration nulled unknowable dates; such a row cannot be placed in or
            # out of the window, so it abstains rather than defaulting into it.
            excluded_undated_rows += 1
            continue
        if not (window_start <= trade.transaction_date <= as_of):
            continue
        if trade.owner_cik in routine:
            excluded_routine.add(trade.owner_cik)
            continue
        # The published effect is an officer/director effect; a bare 10% holder is usually a
        # fund rebalancing, so it counts only when the caller opts in.
        counts_by_role = (
            trade.is_officer
            or trade.is_director
            or (trade.is_ten_percent_owner and include_ten_percent_owners)
        )
        if not counts_by_role:
            if trade.is_ten_percent_owner:
                excluded_ten_percent.add(trade.owner_cik)
            continue
        if _purchase_years(public, trade.owner_cik, cutoff) < min_consecutive_years:
            thin_history.add(trade.owner_cik)
            if not include_thin_history:
                continue
        by_owner[trade.owner_cik].append(trade)

    purchases = sum(len(rows) for rows in by_owner.values())
    officer_buyers = sum(1 for rows in by_owner.values() if any(r.is_officer for r in rows))
    director_buyers = sum(1 for rows in by_owner.values() if any(r.is_director for r in rows))

    values = [
        (row.shares or 0.0) * row.price_per_share
        for rows in by_owner.values()
        for row in rows
        if row.price_per_share is not None and row.price_per_share > 0
    ]
    priced_rows = len(values)
    aggregate_value_usd = sum(values) if values else None
    value_is_partial = priced_rows < purchases

    stake_increases: list[float] = []
    for rows in by_owner.values():
        bought = sum(row.shares or 0.0 for row in rows)
        latest = max(rows, key=lambda row: row.transaction_date or dt.date.min)
        owned_after = latest.shares_owned_after
        if owned_after is not None and owned_after > 0:
            # Share of the insider's reported post-trade holding this window represents. Capped
            # at 100: an indirect-ownership row can report a holding smaller than the purchase.
            stake_increases.append(min(100.0, bought / owned_after * 100.0))
    median_stake_increase_pct = _median(stake_increases)

    dates = [row.transaction_date for rows in by_owner.values() for row in rows]
    qualifying_buyers = len(by_owner)
    score = min(
        100,
        _breadth_points(qualifying_buyers)
        + _role_points(officer_buyers, director_buyers)
        + _conviction_points(median_stake_increase_pct)
        + _size_points(aggregate_value_usd),
    )

    read = FintelInsiderRead(
        as_of=as_of,
        window_days=window_days,
        band=_band(qualifying_buyers),
        score=score if qualifying_buyers else 0,
        qualifying_buyers=qualifying_buyers,
        officer_buyers=officer_buyers,
        director_buyers=director_buyers,
        purchases=purchases,
        first_purchase_on=min(dates) if dates else None,
        last_purchase_on=max(dates) if dates else None,
        aggregate_value_usd=aggregate_value_usd,
        value_is_partial=value_is_partial,
        median_stake_increase_pct=median_stake_increase_pct,
        excluded_plan_rows=excluded_plan_rows,
        excluded_routine_buyers=len(excluded_routine),
        excluded_ten_percent_buyers=len(excluded_ten_percent),
        excluded_undated_rows=excluded_undated_rows,
        thin_history_buyers=len(thin_history),
        known_through=known_through,
    )
    return _with_evidence(read)


def _with_evidence(read: FintelInsiderRead) -> FintelInsiderRead:
    """Attach descriptive sentences. Statements of what was filed — never a recommendation."""
    lines: list[str] = []
    if read.qualifying_buyers and read.first_purchase_on and read.last_purchase_on:
        span = (
            f"on {read.first_purchase_on}"
            if read.first_purchase_on == read.last_purchase_on
            else f"between {read.first_purchase_on} and {read.last_purchase_on}"
        )
        plural = "insider" if read.qualifying_buyers == 1 else "insiders"
        lines.append(
            f"{read.qualifying_buyers} {plural} bought on the open market {span} "
            f"({read.purchases} purchase{'' if read.purchases == 1 else 's'})."
        )
        roles = []
        if read.officer_buyers:
            roles.append(f"{read.officer_buyers} officer{'' if read.officer_buyers == 1 else 's'}")
        if read.director_buyers:
            roles.append(
                f"{read.director_buyers} director{'' if read.director_buyers == 1 else 's'}"
            )
        if roles:
            lines.append(" and ".join(roles) + " among the buyers.")
        if read.aggregate_value_usd is not None:
            qualifier = " for the rows that disclosed a price" if read.value_is_partial else ""
            lines.append(f"Aggregate disclosed value ${read.aggregate_value_usd:,.0f}{qualifier}.")
        if read.median_stake_increase_pct is not None:
            lines.append(
                f"Median buyer raised their reported holding by "
                f"{read.median_stake_increase_pct:.1f}%."
            )
    else:
        lines.append(
            f"No open-market insider purchase survived the filters in the "
            f"{read.window_days} days to {read.as_of}."
        )

    if read.excluded_plan_rows:
        lines.append(
            f"{read.excluded_plan_rows} row{'' if read.excluded_plan_rows == 1 else 's'} "
            "excluded as Rule 10b5-1 scheduled trades."
        )
    if read.excluded_routine_buyers:
        lines.append(
            f"{read.excluded_routine_buyers} buyer"
            f"{'' if read.excluded_routine_buyers == 1 else 's'} excluded as calendar-routine."
        )
    if read.excluded_ten_percent_buyers:
        lines.append(
            f"{read.excluded_ten_percent_buyers} 10% owner"
            f"{'' if read.excluded_ten_percent_buyers == 1 else 's'} excluded (not an "
            "officer or director)."
        )
    if read.excluded_undated_rows:
        lines.append(
            f"{read.excluded_undated_rows} row{'' if read.excluded_undated_rows == 1 else 's'} "
            "had no usable transaction date and was not placed in the window."
        )
    if read.thin_history_buyers:
        lines.append(
            f"{read.thin_history_buyers} buyer{'' if read.thin_history_buyers == 1 else 's'} "
            "had too little history to test for a calendar programme."
        )
    return replace(read, evidence=lines)
