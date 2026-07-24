"""Read model for the squeeze monitor (docs/research/squeeze-research-2026-07-24.md).

Serves the append-only ``squeeze_daily_states`` archive for the requesting tenant's market
only, alongside the *registered blocked families* so absent datasets are an explicit product
answer, not a hidden gap. Discovery performance (return / MFE / MAE) is derived from completed
bars from first discovery through the selected archive date — the same basis rules as the
decision archive, including the DSE raw-close caveat. Read-only; the scan task is the only
writer. No LLM anywhere.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.institutional_research.decision_board import (
    adjusted_close,
    discovery_performance,
)
from api.institutional_research.schemas import (
    SqueezeEntryOut,
    SqueezeFamilyOut,
    SqueezeMonitorOut,
)
from bulls.analytics.squeeze_monitor import FAMILY_LABELS
from bulls.analytics.strategy_readiness import STRATEGY_READINESS
from bulls.core.models import DailyBar, SqueezeDailyState, Symbol, TickerAnalytics

_STATE_ORDER = {
    "confirmed": 0,
    "trigger_ready": 1,
    "forming": 2,
    "watch": 3,
    "exhausted": 4,
    "failed": 5,
}

LIMITATIONS = [
    "FINRA daily short-marked volume is not short interest, cannot establish open short "
    "positions or days-to-cover, and appears only as labeled supporting context.",
    "Atlas has no borrow, locate, cost-to-borrow, failures-to-deliver, or options data; the "
    "families that require them are shown as data-blocked, never approximated.",
    "13F institutional ownership is delayed quarterly disclosure, never live flow.",
    "States are a diagnostic taxonomy (squeeze-monitor-v1); no backtest has validated them "
    "and nothing here is a prediction or a recommendation.",
    "A 2R planning objective is risk geometry from the trigger/invalidation pair, not a "
    "price forecast.",
]

_BLOCKED_FAMILY_KEYS = {
    "US": ("us_short_squeeze", "us_gamma_squeeze", "us_float_liquidity_squeeze"),
    "DSE": (),
}


def _blocked_families(market: str) -> list[SqueezeFamilyOut]:
    blocked: list[SqueezeFamilyOut] = []
    for key in _BLOCKED_FAMILY_KEYS.get(market, ()):
        entry = STRATEGY_READINESS.get(key)
        if entry is None:
            continue
        blocked.append(
            SqueezeFamilyOut(
                family=key,
                label=entry.name,
                status="data_blocked",
                blocked_reason=entry.rationale,
                missing_datasets=[item.description for item in entry.missing_data],
                entries=[],
            )
        )
    return blocked


async def load_squeeze_monitor(
    session: AsyncSession,
    *,
    tenant_id: str,
    market: str,
    as_of: dt.date | None = None,
) -> SqueezeMonitorOut:
    available_dates = list(
        await session.scalars(
            select(SqueezeDailyState.as_of_date)
            .where(SqueezeDailyState.market == market)
            .distinct()
            .order_by(SqueezeDailyState.as_of_date.desc())
            .limit(260)
        )
    )
    latest_date = available_dates[0] if available_dates else None
    eligible = [value for value in available_dates if as_of is None or value <= as_of]
    selected_date = eligible[0] if eligible else None

    methodology = (
        "States come from the append-only squeeze-monitor-v1 archive written once per "
        "completed session after the analytics refresh. Discovery performance uses completed "
        "closes (split/distribution-adjusted where audited factors exist — US yes, DSE raw "
        "closes) from first discovery through the selected archive date. Blocked families are "
        "registered with their exact missing datasets."
    )

    if selected_date is None:
        return SqueezeMonitorOut(
            market=market,
            tenant_id=tenant_id,
            generated_at=dt.datetime.now(dt.UTC),
            selected_date=None,
            latest_date=latest_date,
            available_dates=available_dates,
            families=_blocked_families(market),
            methodology=methodology,
            limitations=LIMITATIONS,
        )

    rows = list(
        await session.scalars(
            select(SqueezeDailyState).where(
                SqueezeDailyState.market == market,
                SqueezeDailyState.as_of_date == selected_date,
                # "none" rows exist only to close out a previously live episode in the archive;
                # they are bookkeeping, not a listable setup.
                SqueezeDailyState.state != "none",
            )
        )
    )
    codes = sorted({row.code for row in rows})
    symbols = {
        symbol.code: symbol
        for symbol in await session.scalars(
            select(Symbol).where(Symbol.market == market, Symbol.code.in_(codes))
        )
    }
    analytics_by_code = {
        row.code: row
        for row in await session.scalars(
            select(TickerAnalytics).where(
                TickerAnalytics.market == market, TickerAnalytics.code.in_(codes)
            )
        )
    }
    earliest = min((row.first_discovered_on for row in rows), default=selected_date)
    bars = list(
        await session.scalars(
            select(DailyBar)
            .where(
                DailyBar.market == market,
                DailyBar.code.in_(codes),
                DailyBar.date >= earliest,
                DailyBar.date <= selected_date,
            )
            .order_by(DailyBar.code, DailyBar.date)
        )
    )
    bars_by_code: dict[str, list[DailyBar]] = defaultdict(list)
    for bar in bars:
        bars_by_code[bar.code].append(bar)

    entries_by_family: dict[str, list[SqueezeEntryOut]] = defaultdict(list)
    for row in rows:
        code_bars = bars_by_code.get(row.code, [])
        path = [
            adjusted_close(bar)
            for bar in code_bars
            if row.first_discovered_on <= bar.date <= selected_date
        ]
        discovery_bar = next(
            (bar for bar in reversed(code_bars) if bar.date <= row.first_discovered_on), None
        )
        discovery_price = adjusted_close(discovery_bar) if discovery_bar is not None else None
        as_of_bar = code_bars[-1] if code_bars else None
        return_pct, favorable, adverse = discovery_performance(
            path, reference_price=discovery_price
        )
        analytics = analytics_by_code.get(row.code)
        capacity = "Liquidity capacity unavailable."
        if (
            analytics is not None
            and analytics.avg_volume_20 is not None
            and analytics.last_close is not None
        ):
            capacity_value = analytics.avg_volume_20 * analytics.last_close * 0.02 / 1_000_000
            capacity = (
                f"About {capacity_value:.2f}M per session at 2% of 20-session average traded "
                "value."
            )
        evidence = row.evidence or {}
        entries_by_family[row.family].append(
            SqueezeEntryOut(
                market=market,
                code=row.code,
                company=symbols[row.code].name_en if row.code in symbols else row.code,
                cap_tier=(
                    analytics.cap_tier
                    if analytics is not None and analytics.cap_tier
                    else "unclassified"
                ),
                family=row.family,
                family_label=FAMILY_LABELS.get(row.family, row.family),
                state=row.state,
                previous_state=row.previous_state,
                state_reason=row.reason,
                is_new=row.first_discovered_on == selected_date,
                first_discovered_on=row.first_discovered_on,
                as_of_date=row.as_of_date,
                sessions_since_discovery=len(path),
                discovery_price=discovery_price,
                as_of_price=adjusted_close(as_of_bar) if as_of_bar is not None else None,
                return_since_discovery_pct=return_pct,
                max_favorable_pct=favorable,
                max_adverse_pct=adverse,
                setup_price=row.setup_price,
                trigger_price=row.trigger_price,
                invalidation_price=row.invalidation_price,
                risk_per_share=row.risk_per_share,
                planning_objective_price=row.planning_objective_price,
                planning_reward_risk=2.0 if row.planning_objective_price is not None else None,
                expected_holding=str(
                    evidence.get("expected_holding", "Defined by the family specification")
                ),
                liquidity_capacity_note=capacity,
                supporting_evidence=[str(item) for item in evidence.get("supporting", [])],
                counter_evidence=[str(item) for item in evidence.get("counter", [])],
                data_quality=[str(item) for item in evidence.get("data_quality", [])],
                missing_evidence=[str(item) for item in evidence.get("missing", [])],
                paper_book_status=(
                    "Maps to the registered us_breakout_v1 paper book."
                    if market == "US" and row.family == "compression_breakout"
                    else "No paper book — pending family diagnostics."
                ),
                methodology_version=row.methodology_version,
            )
        )

    families: list[SqueezeFamilyOut] = []
    for family, label in FAMILY_LABELS.items():
        if family == "supply_constrained_breakout" and market != "DSE":
            continue
        entries = entries_by_family.get(family, [])
        entries.sort(
            key=lambda entry: (
                _STATE_ORDER.get(entry.state, 9),
                not entry.is_new,
                entry.code,
            )
        )
        families.append(
            SqueezeFamilyOut(family=family, label=label, status="available", entries=entries)
        )
    families.extend(_blocked_families(market))

    return SqueezeMonitorOut(
        market=market,
        tenant_id=tenant_id,
        generated_at=dt.datetime.now(dt.UTC),
        selected_date=selected_date,
        latest_date=latest_date,
        available_dates=available_dates,
        families=families,
        methodology=methodology,
        limitations=LIMITATIONS,
    )
