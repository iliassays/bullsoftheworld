"""Read model for the squeeze monitor (docs/research/squeeze-research-2026-07-24.md).

Serves the ``squeeze_daily_states`` archive for the requesting tenant's market
only, alongside the *registered blocked families* so absent datasets are an explicit product
answer, not a hidden gap. Discovery performance (return / MFE / MAE) is derived from completed
bars from first discovery through the selected archive date — the same basis rules as the
decision archive, including the DSE raw-close caveat. Read-only; the scan task is the only
writer. No LLM anywhere.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.institutional_research.decision_board import (
    adjusted_close,
    discovery_performance,
)
from api.institutional_research.schemas import (
    SqueezeChartPointOut,
    SqueezeEntryOut,
    SqueezeFamilyOut,
    SqueezeMonitorOut,
    SqueezePathOut,
    SqueezeStateMarkerOut,
)
from bulls.analytics.chart_overlays import (
    anchored_vwap,
    atr_contraction,
    exponential_moving_average,
)
from bulls.analytics.squeeze_monitor import FAMILY_LABELS
from bulls.analytics.strategy_readiness import STRATEGY_READINESS
from bulls.core.models import DailyBar, SqueezeDailyState, Symbol

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
    "States are a diagnostic taxonomy (squeeze-monitor-v2); no backtest has validated them "
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
                # A family whose datasets have landed is no longer "data blocked" even if no
                # evaluator exists for it yet — saying otherwise would misreport the reason.
                status="data_blocked" if entry.status == "blocked" else "not_implemented",
                blocked_reason=entry.rationale,
                missing_datasets=[item.description for item in entry.missing_data],
                entries=[],
            )
        )
    return blocked


def _build_entry(
    row: SqueezeDailyState,
    *,
    market: str,
    company: str,
    code_bars: list[DailyBar],
    selected_date: dt.date,
) -> SqueezeEntryOut:
    """Build one entry from an archived row plus that code's completed bars.

    Shared by the board and the single-setup path so a chart request does not have to
    rebuild every family's entries to find one row.
    """

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
    return_pct, favorable, adverse = discovery_performance(path, reference_price=discovery_price)
    # Classification comes from the archived row, not from current analytics: reading the
    # live single-row table made an archived screen change after the fact and show a tier
    # the market did not have on that session.
    capacity = (
        "Liquidity capacity was not recorded for this archived session."
        if row.average_dollar_volume_mn is None
        else (
            f"About {row.average_dollar_volume_mn * 0.02:.2f}M per session at 2% of the "
            "20-session average traded value recorded on this session."
        )
    )
    evidence = row.evidence or {}
    return SqueezeEntryOut(
        market=market,
        code=row.code,
        company=company,
        cap_tier=row.cap_tier or "unclassified",
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
        # No squeeze family feeds any book. us_breakout_v1 trades its own signals on
        # its own schedule; claiming this monitor "maps to" it implied an integration
        # that does not exist.
        paper_book_status=(
            "No paper book. This is archived research evidence, not a trade candidate; "
            "no squeeze family has run its historical diagnostics."
        ),
        methodology_version=row.methodology_version,
    )


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
        "States come from the squeeze-monitor-v2 archive written once per "
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
        entries_by_family[row.family].append(
            _build_entry(
                row,
                market=market,
                company=symbols[row.code].name_en if row.code in symbols else row.code,
                code_bars=bars_by_code.get(row.code, []),
                selected_date=selected_date,
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


class _AdjustedBar:
    """Split/distribution-adjusted OHLCV view of one stored bar.

    US bars carry audited adjustment factors; DSE bars do not, so the ratio is 1.0 there and
    the caller states the raw-close caveat. Applying the close ratio across the whole bar keeps
    the candle internally consistent — adjusting the close alone would distort every wick.
    """

    __slots__ = ("close", "date", "high", "low", "open", "volume")

    def __init__(self, bar: DailyBar) -> None:
        close = float(bar.close)
        adjusted = float(bar.adjusted_close) if bar.adjusted_close is not None else close
        ratio = adjusted / close if close > 0 else 1.0
        self.date = bar.date
        self.open = float(bar.open) * ratio
        self.high = float(bar.high) * ratio
        self.low = float(bar.low) * ratio
        self.close = adjusted
        self.volume = float(bar.volume)


async def load_squeeze_path(
    session: AsyncSession,
    *,
    tenant_id: str,
    market: str,
    family: str,
    code: str,
    as_of: dt.date | None = None,
) -> SqueezePathOut:
    """Load candles, overlays and the archived state progression for one squeeze setup.

    The entry is resolved from the same archive read the list uses, so the chart can never show
    a setup the board is not showing. Raises LookupError when the code is absent from the
    selected session's archive.
    """

    normalized = code.strip().upper()
    # Scoped to one setup. Rebuilding the whole board here meant every chart click re-ran the
    # full multi-family query and loaded every code's bars to find a single row.
    selected_date = await session.scalar(
        select(func.max(SqueezeDailyState.as_of_date)).where(
            SqueezeDailyState.market == market,
            SqueezeDailyState.state != "none",
            *([SqueezeDailyState.as_of_date <= as_of] if as_of is not None else []),
        )
    )
    if selected_date is None:
        raise LookupError("squeeze setup not found in this archived session")
    row = await session.scalar(
        select(SqueezeDailyState).where(
            SqueezeDailyState.market == market,
            SqueezeDailyState.code == normalized,
            SqueezeDailyState.family == family,
            SqueezeDailyState.as_of_date == selected_date,
            SqueezeDailyState.state != "none",
        )
    )
    if row is None:
        raise LookupError("squeeze setup not found in this archived session")
    symbol = await session.scalar(
        select(Symbol).where(Symbol.market == market, Symbol.code == normalized)
    )
    entry_bars = list(
        await session.scalars(
            select(DailyBar)
            .where(
                DailyBar.market == market,
                DailyBar.code == normalized,
                DailyBar.date >= row.first_discovered_on,
                DailyBar.date <= selected_date,
            )
            .order_by(DailyBar.date)
        )
    )
    entry = _build_entry(
        row,
        market=market,
        company=symbol.name_en if symbol is not None else normalized,
        code_bars=entry_bars,
        selected_date=selected_date,
    )

    # Context before discovery is what makes a base readable; the window never extends past the
    # archived session, so an archived date cannot render future price action.
    context_start = entry.first_discovered_on - dt.timedelta(days=240)
    rows = list(
        await session.scalars(
            select(DailyBar)
            .where(
                DailyBar.market == market,
                DailyBar.code == normalized,
                DailyBar.date >= context_start,
                DailyBar.date <= entry.as_of_date,
            )
            .order_by(DailyBar.date)
        )
    )
    bars = [_AdjustedBar(row) for row in rows]
    closes = [bar.close for bar in bars]
    ema_20 = exponential_moving_average(closes, 20)
    ema_50 = exponential_moving_average(closes, 50)
    anchor = next(
        (index for index, bar in enumerate(bars) if bar.date >= entry.first_discovered_on),
        len(bars),
    )
    vwap = anchored_vwap(bars, anchor_index=anchor)
    atr_now, atr_prior, atr_change = atr_contraction(bars)

    history = list(
        await session.scalars(
            select(SqueezeDailyState)
            .where(
                SqueezeDailyState.market == market,
                SqueezeDailyState.code == normalized,
                SqueezeDailyState.family == family,
                SqueezeDailyState.as_of_date <= selected_date,
                SqueezeDailyState.as_of_date >= entry.first_discovered_on,
            )
            .order_by(SqueezeDailyState.as_of_date)
        )
    )

    # Each distinct first_discovered_on for this ticker/family is one discovery episode. The
    # current one is entry.first_discovered_on; anything earlier is a prior discovery.
    episode_dates = list(
        await session.scalars(
            select(SqueezeDailyState.first_discovered_on)
            .where(
                SqueezeDailyState.market == market,
                SqueezeDailyState.code == normalized,
                SqueezeDailyState.family == family,
                SqueezeDailyState.as_of_date <= selected_date,
            )
            .distinct()
            .order_by(SqueezeDailyState.first_discovered_on)
        )
    )
    prior_discovery_dates = [value for value in episode_dates if value < entry.first_discovered_on]
    discovery_number = len(prior_discovery_dates) + 1

    return SqueezePathOut(
        market=market,
        tenant_id=tenant_id,
        family=family,
        family_label=entry.family_label,
        entry=entry,
        points=[
            SqueezeChartPointOut(
                date=bar.date,
                open=round(bar.open, 6),
                high=round(bar.high, 6),
                low=round(bar.low, 6),
                close=round(bar.close, 6),
                volume=int(bar.volume),
                ema_20=round(ema_20[index], 6) if ema_20[index] is not None else None,
                ema_50=round(ema_50[index], 6) if ema_50[index] is not None else None,
                anchored_vwap=round(vwap[index], 6) if vwap[index] is not None else None,
            )
            for index, bar in enumerate(bars)
        ],
        # Only transitions carry information; repeating an unchanged state every session would
        # bury the progression the user is trying to read.
        state_history=[
            SqueezeStateMarkerOut(
                date=row.as_of_date,
                state=row.state,
                previous_state=row.previous_state,
                reason=row.reason,
            )
            for row in history
            if row.state != row.previous_state
        ],
        discovery_number=discovery_number,
        prior_discovery_dates=prior_discovery_dates,
        atr_14=round(atr_now, 6) if atr_now is not None else None,
        atr_14_prior=round(atr_prior, 6) if atr_prior is not None else None,
        atr_change_pct=round(atr_change, 3) if atr_change is not None else None,
        price_basis=(
            "Split/distribution-adjusted completed sessions."
            if market == "US"
            else "Raw completed DSE exchange closes — no corporate-action adjustment exists, "
            "so a bonus or rights ex-date appears as a price drop."
        ),
        overlay_basis=(
            "EMA 20/50 from completed closes. Anchored VWAP is computed from daily typical "
            "price x volume anchored at first discovery — Atlas has no intraday history, so "
            "this is not an intraday session VWAP."
        ),
    )
