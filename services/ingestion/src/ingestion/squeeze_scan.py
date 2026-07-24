"""EOD squeeze-taxonomy scan — the only writer of ``squeeze_daily_states``.

Runs after the market's analytics refresh. Deterministic: loads completed bars + the persisted
analytics row per eligible symbol, injects the prior archived state per family, evaluates the
pure ``squeeze_monitor`` engine, and appends today's states. Only meaningful rows are archived:
a state other than ``none``, or a transition out of a previously archived state (so failures and
exhaustions are recorded even when the setup disappears).

One-shot:
    uv run python -m ingestion.squeeze_scan DSE
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import sys
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.analytics.research_strategy import RISK_POLICIES
from bulls.analytics.squeeze_monitor import (
    METHODOLOGY_VERSION,
    SqueezeBar,
    SqueezeInputs,
    evaluate_compression_breakout,
    evaluate_failed_breakdown,
    evaluate_supply_constrained,
)
from bulls.core.db import get_sessionmaker
from bulls.core.models import (
    DailyBar,
    EdgarFilingEvent,
    InsiderTransaction,
    SecurityMaster,
    ShortVolumeDaily,
    SqueezeDailyState,
    TickerAnalytics,
)

log = logging.getLogger(__name__)

_BAR_LOOKBACK_SESSIONS = 130
_DILUTION_FORMS = ("S-1", "S-3", "424B1", "424B2", "424B3", "424B4", "424B5", "S-1/A", "S-3/A")
_EVALUATORS = {
    "compression_breakout": evaluate_compression_breakout,
    "failed_breakdown_reversal": evaluate_failed_breakdown,
    "supply_constrained_breakout": evaluate_supply_constrained,
}


def _families_for(market: str) -> list[str]:
    families = ["compression_breakout", "failed_breakdown_reversal"]
    if market == "DSE":
        families.append("supply_constrained_breakout")
    return families


async def run_squeeze_scan(market: str) -> dict[str, int]:
    market = market.upper()
    families = _families_for(market)
    policy = RISK_POLICIES[market]
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        session_date = await session.scalar(
            select(func.max(TickerAnalytics.as_of_date)).where(TickerAnalytics.market == market)
        )
        if session_date is None:
            return {"evaluated": 0, "archived": 0}
        analytics_rows = list(
            await session.scalars(
                select(TickerAnalytics).where(
                    TickerAnalytics.market == market,
                    TickerAnalytics.as_of_date == session_date,
                    TickerAnalytics.avg_volume_20.is_not(None),
                    TickerAnalytics.last_close * TickerAnalytics.avg_volume_20
                    >= policy.minimum_average_daily_value_mn * 1_000_000,
                )
            )
        )
        if not analytics_rows:
            return {"evaluated": 0, "archived": 0}
        codes = sorted(row.code for row in analytics_rows)

        bar_floor = session_date - dt.timedelta(days=_BAR_LOOKBACK_SESSIONS * 2)
        bars_by_code: dict[str, list[SqueezeBar]] = defaultdict(list)
        for start in range(0, len(codes), 400):
            chunk = codes[start : start + 400]
            bar_rows = (
                await session.execute(
                    select(
                        DailyBar.code,
                        DailyBar.date,
                        DailyBar.open,
                        DailyBar.high,
                        DailyBar.low,
                        DailyBar.close,
                        DailyBar.volume,
                        DailyBar.adjusted_close,
                    )
                    .where(
                        DailyBar.market == market,
                        DailyBar.code.in_(chunk),
                        DailyBar.date >= bar_floor,
                        DailyBar.date <= session_date,
                    )
                    .order_by(DailyBar.code, DailyBar.date)
                )
            ).all()
            for row in bar_rows:
                adjustment = (
                    float(row.adjusted_close) / float(row.close)
                    if row.adjusted_close is not None and row.close and row.close > 0
                    else 1.0
                )
                if row.open <= 0 or row.high <= 0 or row.low <= 0 or row.close <= 0:
                    continue
                bars_by_code[row.code].append(
                    SqueezeBar(
                        date=row.date,
                        open=float(row.open) * adjustment,
                        high=float(row.high) * adjustment,
                        low=float(row.low) * adjustment,
                        close=float(row.close) * adjustment,
                        volume=float(row.volume),
                    )
                )

        # Prior archived state per (code, family): the latest row strictly before this session.
        prior_rows = (
            await session.execute(
                select(
                    SqueezeDailyState.code,
                    SqueezeDailyState.family,
                    SqueezeDailyState.state,
                    SqueezeDailyState.trigger_price,
                    SqueezeDailyState.first_discovered_on,
                )
                .where(
                    SqueezeDailyState.market == market,
                    SqueezeDailyState.code.in_(codes),
                    SqueezeDailyState.as_of_date < session_date,
                )
                .distinct(SqueezeDailyState.code, SqueezeDailyState.family)
                .order_by(
                    SqueezeDailyState.code,
                    SqueezeDailyState.family,
                    SqueezeDailyState.as_of_date.desc(),
                )
            )
        ).all()
        prior_by_pair = {(row.code, row.family): row for row in prior_rows}

        short_share_by_code: dict[str, float] = {}
        dilution_codes: set[str] = set()
        insider_selling_codes: set[str] = set()
        if market == "US":
            short_rows = (
                await session.execute(
                    select(
                        ShortVolumeDaily.code,
                        func.sum(ShortVolumeDaily.short_volume),
                        func.sum(ShortVolumeDaily.total_volume),
                    )
                    .where(
                        ShortVolumeDaily.market == "US",
                        ShortVolumeDaily.code.in_(codes),
                        ShortVolumeDaily.date > session_date - dt.timedelta(days=9),
                        ShortVolumeDaily.date <= session_date,
                    )
                    .group_by(ShortVolumeDaily.code)
                )
            ).all()
            for code, short_volume, total_volume in short_rows:
                if total_volume and float(total_volume) > 0:
                    short_share_by_code[code] = float(short_volume) / float(total_volume)
            cik_rows = (
                await session.execute(
                    select(SecurityMaster.symbol, SecurityMaster.cik).where(
                        SecurityMaster.market == "US",
                        SecurityMaster.symbol.in_(codes),
                        SecurityMaster.cik.is_not(None),
                    )
                )
            ).all()
            symbol_by_cik: dict[str, list[str]] = defaultdict(list)
            for symbol, cik in cik_rows:
                symbol_by_cik[cik].append(symbol)
            if symbol_by_cik:
                filing_floor = dt.datetime.combine(
                    session_date - dt.timedelta(days=90), dt.time.min, tzinfo=dt.UTC
                )
                filing_rows = (
                    await session.execute(
                        select(EdgarFilingEvent.cik)
                        .where(
                            EdgarFilingEvent.cik.in_(list(symbol_by_cik)),
                            EdgarFilingEvent.form.in_(_DILUTION_FORMS),
                            EdgarFilingEvent.accepted_at >= filing_floor,
                        )
                        .distinct()
                    )
                ).all()
                for (cik,) in filing_rows:
                    dilution_codes.update(symbol_by_cik[cik])
                selling_floor = dt.datetime.combine(
                    session_date - dt.timedelta(days=30), dt.time.min, tzinfo=dt.UTC
                )
                selling_rows = (
                    await session.execute(
                        select(InsiderTransaction.issuer_symbol)
                        .join(
                            EdgarFilingEvent,
                            EdgarFilingEvent.accession_number
                            == InsiderTransaction.accession_number,
                        )
                        .where(
                            InsiderTransaction.issuer_symbol.in_(codes),
                            InsiderTransaction.code == "S",
                            EdgarFilingEvent.accepted_at >= selling_floor,
                        )
                        .distinct()
                    )
                ).all()
                insider_selling_codes = {row[0] for row in selling_rows}

        evaluated = 0
        payloads: list[dict] = []
        for analytics in analytics_rows:
            bars = bars_by_code.get(analytics.code, [])
            if len(bars) < 60 or bars[-1].date != session_date:
                continue
            evaluated += 1
            for family in families:
                prior = prior_by_pair.get((analytics.code, family))
                inputs = SqueezeInputs(
                    market=market,  # type: ignore[arg-type]
                    code=analytics.code,
                    bars=bars[-_BAR_LOOKBACK_SESSIONS:],
                    last_close=bars[-1].close,
                    sma_50=analytics.sma_50,
                    sma_200=analytics.sma_200,
                    pct_from_52w_high=analytics.pct_from_52w_high,
                    relative_volume=analytics.relative_volume,
                    rel_volume_5d=analytics.rel_volume_5d,
                    cmf_20=analytics.cmf_20,
                    obv_slope=analytics.obv_slope,
                    avg_volume_20=analytics.avg_volume_20,
                    market_cap_mn=analytics.market_cap_mn,
                    free_float_cap_mn=analytics.free_float_cap_mn,
                    sponsor_pct=analytics.sponsor_pct,
                    institute_delta=analytics.institute_delta,
                    foreign_delta=analytics.foreign_delta,
                    short_marked_share_5d=short_share_by_code.get(analytics.code),
                    recent_dilution_filing=analytics.code in dilution_codes,
                    insider_net_selling_30d=analytics.code in insider_selling_codes,
                    prior_state=prior.state if prior is not None else "none",
                    prior_trigger_price=prior.trigger_price if prior is not None else None,
                )
                assessment = _EVALUATORS[family](inputs)
                previous_state = prior.state if prior is not None else "none"
                if assessment.state == "none" and previous_state in ("none", "failed", "exhausted"):
                    continue  # nothing to archive: no setup, and no live state to close out
                first_discovered = (
                    prior.first_discovered_on
                    if prior is not None and previous_state not in ("none",)
                    else session_date
                )
                payloads.append(
                    {
                        "market": market,
                        "code": analytics.code,
                        "family": family,
                        "as_of_date": session_date,
                        "state": assessment.state,
                        "previous_state": previous_state,
                        "reason": assessment.reason[:500],
                        "setup_price": assessment.setup_price,
                        "trigger_price": assessment.trigger_price,
                        "invalidation_price": assessment.invalidation_price,
                        "risk_per_share": assessment.risk_per_share,
                        "planning_objective_price": assessment.planning_objective_price,
                        "first_discovered_on": first_discovered,
                        "evidence": {
                            "supporting": assessment.supporting_evidence,
                            "counter": assessment.counter_evidence,
                            "data_quality": assessment.data_quality,
                            "missing": assessment.missing_evidence,
                            "expected_holding": assessment.expected_holding,
                        },
                        "methodology_version": METHODOLOGY_VERSION,
                    }
                )

        archived = 0
        for start in range(0, len(payloads), 500):
            chunk = payloads[start : start + 500]
            statement = pg_insert(SqueezeDailyState).values(chunk)
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=["market", "code", "family", "as_of_date"],
                    set_={
                        column: getattr(statement.excluded, column)
                        for column in (
                            "state",
                            "previous_state",
                            "reason",
                            "setup_price",
                            "trigger_price",
                            "invalidation_price",
                            "risk_per_share",
                            "planning_objective_price",
                            "first_discovered_on",
                            "evidence",
                            "methodology_version",
                        )
                    },
                )
            )
            archived += len(chunk)
        await session.commit()
    log.info(
        "squeeze_scan market=%s session=%s evaluated=%s archived=%s",
        market,
        session_date,
        evaluated,
        archived,
    )
    return {"evaluated": evaluated, "archived": archived}


def main() -> None:
    market = sys.argv[1] if len(sys.argv) > 1 else "DSE"
    counts = asyncio.run(run_squeeze_scan(market))
    print(f"[squeeze] {market}: evaluated {counts['evaluated']}, archived {counts['archived']}")


if __name__ == "__main__":
    main()
