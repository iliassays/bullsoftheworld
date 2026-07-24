"""System B contracts for the forced-seller/post-spin event book.

System B is intentionally data-gated. A generic news item containing "spin-off" is not a
corporate-action history, and current listings cannot reconstruct securities that disappeared.
Until every required history is timestamped and replayable, Atlas registers the hypothesis and
returns a data-blocked diagnostic instead of manufacturing a backtest.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


class ForcedSellerDatasetCoverage(BaseModel):
    """Promotion-critical data contracts for a reconstructible forced-seller event study."""

    corporate_action_history_complete: bool = False
    effective_timestamps_complete: bool = False
    parent_holder_history_complete: bool = False
    post_bankruptcy_distributions_complete: bool = False
    point_in_time_fundamentals_complete: bool = False
    inactive_listing_history_complete: bool = False
    adjusted_price_history_complete: bool = False


class ForcedSellerReadiness(BaseModel):
    status: Literal["ready", "data_blocked"]
    missing_datasets: list[str]
    statement: str


class ForcedSellerEvent(BaseModel):
    """One authoritative distribution event, usable only after its effective timestamp."""

    event_id: str
    child_symbol: str
    parent_symbol: str | None = None
    event_kind: Literal["spin_off", "post_bankruptcy_distribution", "forced_distribution"]
    announced_at: dt.datetime
    effective_at: dt.datetime
    source_url: str
    distribution_ratio: float | None = Field(default=None, gt=0)


_REQUIREMENTS = (
    ("corporate_action_history_complete", "authoritative historical spin-off/distribution events"),
    ("effective_timestamps_complete", "point-in-time announcement and effective timestamps"),
    ("parent_holder_history_complete", "parent-holder/index-membership history at distribution"),
    (
        "post_bankruptcy_distributions_complete",
        "completed post-bankruptcy and forced-distribution history",
    ),
    ("point_in_time_fundamentals_complete", "publication-lagged leverage and quality inputs"),
    ("inactive_listing_history_complete", "inactive, acquired, and delisted listing history"),
    ("adjusted_price_history_complete", "corporate-action-safe price and distribution history"),
)


def assess_forced_seller_readiness(
    coverage: ForcedSellerDatasetCoverage,
) -> ForcedSellerReadiness:
    missing = [
        description
        for field, description in _REQUIREMENTS
        if not getattr(coverage, field)
    ]
    if missing:
        return ForcedSellerReadiness(
            status="data_blocked",
            missing_datasets=missing,
            statement=(
                "System B is registered but cannot be simulated honestly. Atlas will not proxy "
                "official corporate actions with news text or current-universe data."
            ),
        )
    return ForcedSellerReadiness(
        status="ready",
        missing_datasets=[],
        statement="Every required forced-seller dataset is point-in-time and replayable.",
    )
