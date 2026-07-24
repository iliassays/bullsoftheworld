"""System A signal layer: the filings-event follower (institutional study, Phase 12).

This is the signal core of the "13D book" — the first actual strategy logic built on the EDGAR
event stream, as opposed to the ingestion that feeds it. Two sleeves, each a stack of filters the
evidence supports, every one of them computable from EDGAR alone:

**Insider sleeve** (Phase 8 §8.2, Form 4):
1. Open-market purchases only — code ``P``. Lakonishok-Lee (V): purchases inform, sales do not,
   because a sale has a hundred innocent reasons and an open-market buy has one.
2. Drop Rule 10b5-1 plan trades. The 2022 reform's checkbox lets a follower discard pre-scheduled
   trades — a signal-cleaner the classic studies never had.
3. Drop *routine* insiders. Cohen-Malloy-Pomorski (2012, JF — V) is the load-bearing refinement:
   an insider who trades the same calendar month year after year carries ~zero signal and is over
   half of all insider trading; the opportunistic remainder earns the documented abnormal return.
4. Prefer clusters. Several insiders buying in one window beats a single buy (direction credible;
   the circulating magnitudes are vendor-stated, so this ranks rather than promises).

**Activist sleeve** (Phase 8 §8.2, Schedule 13D): a new 13D by a filer with a documented
multi-campaign record. The post-filing drift is peer-reviewed and does not reverse.

**Point-in-time discipline (Phase 13.1.1, binding):** every signal is stamped with the EDGAR
*dissemination* time, never the transaction date. An insider buys on Monday and the Form 4 may
not be public until Wednesday; ranking on the transaction date would be lookahead bias and would
manufacture returns nobody could have captured. Callers must supply ``disseminated_at``.

Nothing here sizes a position or decides to trade — that is the book's job. This module answers
one question: which filing events qualify as signals, and when did each become knowable.
"""

from __future__ import annotations

import datetime as dt
import itertools
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, Field

# Cohen-Malloy-Pomorski classify an insider as routine when they trade in the same calendar month
# across several consecutive years. Below this much history the honest answer is "we cannot tell".
ROUTINE_MINIMUM_YEARS = 3

InsiderClass = Literal["routine", "opportunistic", "unclassified"]


class InsiderTrade(BaseModel):
    """One parsed Form 4 non-derivative transaction, carrying its dissemination stamp."""

    issuer_cik: int
    issuer_symbol: str | None = None
    owner_cik: int
    owner_name: str | None = None
    transaction_date: dt.date
    # When the filing became public on EDGAR — the only timestamp a follower may act on.
    disseminated_at: dt.datetime
    code: str | None = None
    shares: float | None = None
    price_per_share: float | None = None
    is_10b5_1_plan: bool = False
    is_officer: bool = False
    is_director: bool = False
    is_ten_percent_owner: bool = False


class InsiderCluster(BaseModel):
    """Qualifying open-market buying by one or more opportunistic insiders at one issuer."""

    issuer_cik: int
    issuer_symbol: str | None = None
    # Signal time: when the *last* filing in the cluster became public. Acting earlier is
    # impossible, so this is the honest entry stamp.
    signal_at: dt.datetime
    first_disseminated_at: dt.datetime
    distinct_insiders: int
    trade_count: int
    total_shares: float
    total_value: float | None
    # Officers and directors are the informed tier; 10% holders are noisier (Phase 8).
    includes_officer_or_director: bool
    owner_ciks: tuple[int, ...]


class ActivistEvent(BaseModel):
    """A new Schedule 13D by a filer on the curated multi-campaign list."""

    accession_number: str
    subject_cik: int
    subject_name: str
    filed_by_cik: int | None
    filed_by_name: str | None
    form: str
    signal_at: dt.datetime
    percent_of_class: float | None = None
    is_amendment: bool = False


def classify_insider(
    trade_dates: Sequence[dt.date], *, minimum_years: int = ROUTINE_MINIMUM_YEARS
) -> InsiderClass:
    """Routine vs opportunistic, from an insider's own filing history (Cohen-Malloy-Pomorski).

    Routine = traded in the same calendar month in at least ``minimum_years`` *consecutive* years.
    Such insiders are following a personal calendar (comp cycles, scheduled diversification), and
    their trades carry ~zero predictive content.

    Returns ``unclassified`` when the history is too short to judge — the caller decides whether to
    trade an unknown, and the default in this module is not to.
    """
    if minimum_years < 2:
        raise ValueError("minimum_years must be at least 2 to establish a pattern")
    years = {date.year for date in trade_dates}
    if len(years) < minimum_years:
        return "unclassified"

    months: dict[int, set[int]] = defaultdict(set)
    for date in trade_dates:
        months[date.month].add(date.year)
    for year_set in months.values():
        ordered = sorted(year_set)
        run = 1
        for previous, current in itertools.pairwise(ordered):
            run = run + 1 if current == previous + 1 else 1
            if run >= minimum_years:
                return "routine"
        if run >= minimum_years:
            return "routine"
    return "opportunistic"


def classify_insiders(
    history: Iterable[InsiderTrade], *, minimum_years: int = ROUTINE_MINIMUM_YEARS
) -> dict[int, InsiderClass]:
    """Classify every insider in a filing history, keyed by owner CIK.

    History should be the insider's *full* recorded trading, not just purchases: the routine
    pattern shows up in scheduled sales as much as buys.
    """
    dates: dict[int, list[dt.date]] = defaultdict(list)
    for trade in history:
        dates[trade.owner_cik].append(trade.transaction_date)
    return {
        owner: classify_insider(owner_dates, minimum_years=minimum_years)
        for owner, owner_dates in dates.items()
    }


def qualifying_purchases(
    trades: Iterable[InsiderTrade],
    classifications: dict[int, InsiderClass],
    *,
    include_unclassified: bool = False,
) -> list[InsiderTrade]:
    """Apply the evidence-backed Form 4 filter stack: P-code, non-plan, opportunistic.

    Each step is a documented refinement rather than a preference, and each only ever removes
    trades — the stack cannot invent a signal.
    """
    kept: list[InsiderTrade] = []
    allowed: set[InsiderClass] = {"opportunistic"}
    if include_unclassified:
        allowed.add("unclassified")
    for trade in trades:
        if (trade.code or "").upper() != "P":
            continue
        if trade.is_10b5_1_plan:
            continue
        if classifications.get(trade.owner_cik, "unclassified") not in allowed:
            continue
        if not trade.shares or trade.shares <= 0:
            continue
        kept.append(trade)
    return kept


def qualifying_purchases_point_in_time(
    history: Iterable[InsiderTrade],
    *,
    include_unclassified: bool = False,
    minimum_years: int = ROUTINE_MINIMUM_YEARS,
) -> list[InsiderTrade]:
    """Filter purchases using only the owner's history public by each candidate filing.

    A single classification computed from the final database leaks future trading behavior into
    earlier signals. This resolver replays the classification clock: for every candidate purchase,
    the owner is classified from transactions whose dissemination timestamp is no later than that
    purchase. Sales remain part of the classification history, but can never become signals.
    """

    ordered = sorted(history, key=lambda trade: (trade.disseminated_at, trade.owner_cik))
    public_dates: dict[int, list[dt.date]] = defaultdict(list)
    kept: list[InsiderTrade] = []
    allowed: set[InsiderClass] = {"opportunistic"}
    if include_unclassified:
        allowed.add("unclassified")

    for _, same_timestamp in itertools.groupby(ordered, key=lambda trade: trade.disseminated_at):
        batch = list(same_timestamp)
        # All rows in one filing timestamp become public together. Add the whole batch before
        # classifying any one row so row order inside a filing cannot change the result.
        for trade in batch:
            public_dates[trade.owner_cik].append(trade.transaction_date)
        for trade in batch:
            classification = classify_insider(
                public_dates[trade.owner_cik], minimum_years=minimum_years
            )
            if (trade.code or "").upper() != "P":
                continue
            if trade.is_10b5_1_plan or classification not in allowed:
                continue
            if not trade.shares or trade.shares <= 0:
                continue
            kept.append(trade)
    return kept


def detect_clusters(
    purchases: Iterable[InsiderTrade],
    *,
    window_days: int = 30,
    minimum_insiders: int = 1,
) -> list[InsiderCluster]:
    """Group qualifying purchases per issuer into dissemination-time windows.

    A cluster closes when a filing arrives more than ``window_days`` after the cluster's first
    disseminated filing. ``minimum_insiders=1`` keeps singletons (ranked below clusters); raise it
    to 2+ to trade only genuine cluster buying.
    """
    if window_days <= 0:
        raise ValueError("window_days must be positive")
    by_issuer: dict[int, list[InsiderTrade]] = defaultdict(list)
    for trade in purchases:
        by_issuer[trade.issuer_cik].append(trade)

    clusters: list[InsiderCluster] = []
    window = dt.timedelta(days=window_days)
    for issuer_cik, issuer_trades in by_issuer.items():
        ordered = sorted(issuer_trades, key=lambda item: item.disseminated_at)
        bucket: list[InsiderTrade] = []
        for trade in ordered:
            if bucket and trade.disseminated_at - bucket[0].disseminated_at > window:
                clusters.append(_build_cluster(issuer_cik, bucket))
                bucket = []
            bucket.append(trade)
        if bucket:
            clusters.append(_build_cluster(issuer_cik, bucket))

    qualifying = [c for c in clusters if c.distinct_insiders >= minimum_insiders]
    qualifying.sort(key=lambda cluster: cluster.signal_at)
    return qualifying


def _build_cluster(issuer_cik: int, trades: list[InsiderTrade]) -> InsiderCluster:
    owners = tuple(sorted({trade.owner_cik for trade in trades}))
    values = [
        trade.shares * trade.price_per_share
        for trade in trades
        if trade.shares and trade.price_per_share
    ]
    symbol = next((trade.issuer_symbol for trade in trades if trade.issuer_symbol), None)
    return InsiderCluster(
        issuer_cik=issuer_cik,
        issuer_symbol=symbol,
        signal_at=max(trade.disseminated_at for trade in trades),
        first_disseminated_at=min(trade.disseminated_at for trade in trades),
        distinct_insiders=len(owners),
        trade_count=len(trades),
        total_shares=sum(trade.shares or 0.0 for trade in trades),
        # None, not zero: an unpriced filing is unknown value, and the two must not be confused.
        total_value=round(sum(values), 2) if values else None,
        includes_officer_or_director=any(
            trade.is_officer or trade.is_director for trade in trades
        ),
        owner_ciks=owners,
    )


class ActivistRoster(BaseModel):
    """Curated filers with documented multi-campaign records (Phase 1/9 tier).

    Deliberately a hand-curated allow-list, not a screen. Phase 8's reconciliation is that filer
    *selection* is the whole strategy: the aggregate 13D universe carries no reliable edge.
    """

    ciks: frozenset[int] = Field(default_factory=frozenset)
    # Case-insensitive substring matches, for filers whose CIK we have not pinned yet.
    name_fragments: tuple[str, ...] = ()

    def matches(self, *, cik: int | None, name: str | None) -> bool:
        if cik is not None and cik in self.ciks:
            return True
        if name and self.name_fragments:
            haystack = name.casefold()
            return any(fragment.casefold() in haystack for fragment in self.name_fragments)
        return False


def qualifying_activist_events(
    events: Iterable[ActivistEvent],
    roster: ActivistRoster,
    *,
    include_amendments: bool = False,
) -> list[ActivistEvent]:
    """Keep new 13Ds filed by rostered activists.

    Amendments are excluded by default: the documented event-study return attaches to the *initial*
    disclosure of a stake, not to routine position updates.
    """
    kept = [
        event
        for event in events
        if roster.matches(cik=event.filed_by_cik, name=event.filed_by_name)
        and (include_amendments or not event.is_amendment)
    ]
    kept.sort(key=lambda event: event.signal_at)
    return kept
