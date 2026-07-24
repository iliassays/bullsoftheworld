"""Point-in-time short-interest reads and derived ratios.

Pure functions over already-loaded observations so the crowding guard, the squeeze monitor and
any backtest share one selection rule and one set of names.

Two naming rules are load-bearing:

* **Basis is in the name.** Atlas has no verified US free float (0 of ~11k symbols), so ratios
  are computed against point-in-time *shares outstanding*. Because float <= shares outstanding,
  a %-of-outstanding figure is always <= the true %-of-float, which makes a fixed threshold
  *less* likely to trigger — conservative for a long-side crowding screen, and never to be
  relabelled "% of float".
* **Days to cover is recorded, not recomputed.** FINRA publishes it over its own volume window;
  deriving our own from a different average would produce a number that disagrees with the
  published figure while carrying the same name.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ShortInterestObservation:
    """One disseminated settlement-date record for a security."""

    settlement_date: dt.date
    known_at: dt.datetime
    shares_short: float
    days_to_cover: float | None = None
    average_daily_volume: float | None = None
    previous_shares_short: float | None = None


def latest_known(
    observations: Sequence[ShortInterestObservation], *, as_of: dt.date
) -> ShortInterestObservation | None:
    """The most recent observation *disseminated* on or before ``as_of``.

    Selection is on ``known_at``, never ``settlement_date`` — a settlement date is public only
    after its dissemination lag, so selecting on it would leak about a week of hindsight into
    every historical decision.
    """

    cutoff = dt.datetime.combine(as_of, dt.time.max, tzinfo=dt.UTC)
    eligible = [item for item in observations if item.known_at <= cutoff]
    if not eligible:
        return None
    return max(eligible, key=lambda item: (item.known_at, item.settlement_date))


def short_interest_pct_of_shares_outstanding(
    shares_short: float | None, shares_outstanding: float | None
) -> float | None:
    """Short interest as a percentage of point-in-time shares outstanding.

    Returns None rather than a guess when either input is missing or non-positive, so callers
    can distinguish "not crowded" from "unknown".
    """

    if shares_short is None or shares_outstanding is None:
        return None
    if shares_short < 0 or shares_outstanding <= 0:
        return None
    return shares_short / shares_outstanding * 100.0


def short_interest_change_pct(observation: ShortInterestObservation) -> float | None:
    """Percentage change in the open short position versus the prior settlement date."""

    previous = observation.previous_shares_short
    if previous is None or previous <= 0:
        return None
    return (observation.shares_short / previous - 1.0) * 100.0
