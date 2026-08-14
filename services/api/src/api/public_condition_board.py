"""Bounded public projection of Atlas research-condition observations.

Atlas owns the full investigation workflow, calibrations, workspace membership, and alerts.  The
public portal receives only a small tenant/market-bound list of currently observed securities so a
reader can discover which ticker pages deserve deeper research.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bulls.analytics import CONDITION_REGISTRY, METHODOLOGY_VERSION
from bulls.core.models import ResearchConditionTransition, Symbol, TickerAnalytics

PublicConditionKey = Literal[
    "trend_alignment",
    "participation_expansion",
    "controlled_pullback_context",
]

_PUBLIC_CONDITIONS = tuple(
    condition
    for condition in CONDITION_REGISTRY
    if condition.key
    in {
        "trend_alignment",
        "participation_expansion",
        "controlled_pullback_context",
    }
)
_PUBLIC_DATA_STATUS = "ready"


class PublicConditionItemOut(BaseModel):
    code: str
    name: str
    sector: str | None
    cap_tier: str
    observed_on: dt.date
    latest_session_date: dt.date
    reference_close: float
    latest_close: float
    close_return_since_observation_pct: float
    average_daily_value_mn: float | None
    evidence_mode: Literal["forward", "reconstructed"]
    is_new: bool


class PublicConditionGroupOut(BaseModel):
    key: PublicConditionKey
    version: str
    title: str
    category: str
    why_it_matters: str
    limitation: str
    observed_count: int = Field(ge=0)
    new_count: int = Field(ge=0)
    items: list[PublicConditionItemOut]


class PublicConditionBoardOut(BaseModel):
    market: Literal["DSE", "US"]
    as_of_date: dt.date | None
    generated_at: dt.datetime
    methodology_version: str
    cap_tier: str | None
    groups: list[PublicConditionGroupOut]
    disclaimer: str


def _latest_public_transition_subquery(market: str):
    versions = [
        and_(
            ResearchConditionTransition.condition_key == condition.key,
            ResearchConditionTransition.condition_version == condition.version,
        )
        for condition in _PUBLIC_CONDITIONS
    ]
    return (
        select(
            ResearchConditionTransition.code.label("code"),
            ResearchConditionTransition.condition_key.label("condition_key"),
            ResearchConditionTransition.condition_version.label("condition_version"),
            ResearchConditionTransition.as_of_date.label("observed_on"),
            ResearchConditionTransition.reference_close.label("reference_close"),
            ResearchConditionTransition.evidence_mode.label("evidence_mode"),
            ResearchConditionTransition.state.label("state"),
            func.row_number()
            .over(
                partition_by=(
                    ResearchConditionTransition.condition_key,
                    ResearchConditionTransition.condition_version,
                    ResearchConditionTransition.code,
                ),
                order_by=ResearchConditionTransition.as_of_date.desc(),
            )
            .label("transition_rank"),
        )
        .where(
            ResearchConditionTransition.market == market,
            ResearchConditionTransition.methodology_version == METHODOLOGY_VERSION,
            or_(*versions),
        )
        .subquery("latest_public_condition_transitions")
    )


def _public_observation_query(
    market: str,
    *,
    latest_session_date: dt.date | None,
    cap_tier: str | None,
    limit_per_condition: int,
):
    latest = _latest_public_transition_subquery(market)
    average_daily_value_mn = case(
        (
            TickerAnalytics.avg_volume_20.isnot(None),
            TickerAnalytics.avg_volume_20 * TickerAnalytics.last_close / 1_000_000.0,
        ),
        else_=None,
    )
    is_new = and_(
        latest.c.evidence_mode == "forward",
        latest.c.observed_on == latest_session_date,
    )
    conditions = [
        latest.c.transition_rank == 1,
        latest.c.state == "observed",
        Symbol.market == market,
        Symbol.is_active.is_(True),
        Symbol.is_hidden.is_(False),
        Symbol.data_status == _PUBLIC_DATA_STATUS,
        TickerAnalytics.market == market,
    ]
    if cap_tier == "unclassified":
        conditions.append(TickerAnalytics.cap_tier.is_(None))
    elif cap_tier is not None:
        conditions.append(TickerAnalytics.cap_tier == cap_tier)

    source = (
        latest.join(Symbol, and_(Symbol.market == market, Symbol.code == latest.c.code))
        .join(
            TickerAnalytics,
            and_(TickerAnalytics.market == market, TickerAnalytics.code == latest.c.code),
        )
    )
    ranked = (
        select(
            latest.c.condition_key,
            latest.c.condition_version,
            latest.c.code,
            Symbol.name_en,
            Symbol.sector,
            TickerAnalytics.cap_tier,
            latest.c.observed_on,
            TickerAnalytics.as_of_date.label("latest_session_date"),
            latest.c.reference_close,
            TickerAnalytics.last_close.label("latest_close"),
            average_daily_value_mn.label("average_daily_value_mn"),
            latest.c.evidence_mode,
            is_new.label("is_new"),
            func.count().over(partition_by=latest.c.condition_key).label("observed_count"),
            func.count()
            .filter(is_new)
            .over(partition_by=latest.c.condition_key)
            .label("new_count"),
            func.row_number()
            .over(
                partition_by=latest.c.condition_key,
                order_by=(
                    desc(is_new),
                    latest.c.observed_on.desc(),
                    average_daily_value_mn.desc().nullslast(),
                    latest.c.code,
                ),
            )
            .label("public_rank"),
        )
        .select_from(source)
        .where(*conditions)
        .subquery("ranked_public_condition_observations")
    )
    return (
        select(ranked)
        .where(ranked.c.public_rank <= limit_per_condition)
        .order_by(ranked.c.condition_key, ranked.c.public_rank)
    )


def _latest_public_session_date_query(market: str):
    return (
        select(func.max(TickerAnalytics.as_of_date))
        .select_from(TickerAnalytics)
        .join(
            Symbol,
            and_(Symbol.market == market, Symbol.code == TickerAnalytics.code),
        )
        .where(
            TickerAnalytics.market == market,
            Symbol.market == market,
            Symbol.is_active.is_(True),
            Symbol.is_hidden.is_(False),
            Symbol.data_status == _PUBLIC_DATA_STATUS,
        )
    )


async def load_public_condition_board(
    session: AsyncSession,
    *,
    market: Literal["DSE", "US"],
    cap_tier: str | None,
    limit_per_condition: int,
) -> PublicConditionBoardOut:
    latest_session_date = await session.scalar(_latest_public_session_date_query(market))
    rows = (
        await session.execute(
            _public_observation_query(
                market,
                latest_session_date=latest_session_date,
                cap_tier=cap_tier,
                limit_per_condition=limit_per_condition,
            )
        )
    ).all()
    rows_by_condition: dict[str, list] = {condition.key: [] for condition in _PUBLIC_CONDITIONS}
    for row in rows:
        rows_by_condition[row.condition_key].append(row)

    groups: list[PublicConditionGroupOut] = []
    for condition in _PUBLIC_CONDITIONS:
        condition_rows = rows_by_condition[condition.key]
        first = condition_rows[0] if condition_rows else None
        groups.append(
            PublicConditionGroupOut(
                key=condition.key,
                version=condition.version,
                title=condition.title,
                category=condition.category,
                why_it_matters=condition.why_it_matters,
                limitation=condition.limitation,
                observed_count=int(first.observed_count if first else 0),
                new_count=int(first.new_count if first else 0),
                items=[
                    PublicConditionItemOut(
                        code=row.code,
                        name=row.name_en,
                        sector=row.sector,
                        cap_tier=row.cap_tier or "unclassified",
                        observed_on=row.observed_on,
                        latest_session_date=row.latest_session_date,
                        reference_close=row.reference_close,
                        latest_close=row.latest_close,
                        close_return_since_observation_pct=round(
                            (row.latest_close / row.reference_close - 1.0) * 100.0,
                            4,
                        ),
                        average_daily_value_mn=(
                            round(row.average_daily_value_mn, 4)
                            if row.average_daily_value_mn is not None
                            else None
                        ),
                        evidence_mode=row.evidence_mode,
                        is_new=bool(row.is_new),
                    )
                    for row in condition_rows
                ],
            )
        )

    return PublicConditionBoardOut(
        market=market,
        as_of_date=latest_session_date,
        generated_at=dt.datetime.now(dt.UTC),
        methodology_version=METHODOLOGY_VERSION,
        cap_tier=cap_tier,
        groups=groups,
        disclaimer=(
            "A condition observation is completed-session research context, not a trade signal, "
            "probability estimate, target, or order."
        ),
    )
