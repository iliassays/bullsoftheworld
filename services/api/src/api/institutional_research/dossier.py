"""Evidence-first company dossier assembled from tenant-bound normalized facts."""

from __future__ import annotations

import datetime as dt
import statistics
import uuid
from dataclasses import asdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.institutional_research.evidence import EVIDENCE_ADAPTERS
from api.institutional_research.queue import _as_utc, _candidate
from api.institutional_research.schemas import (
    CompanyDossierOut,
    DossierConditionWorkbenchOut,
    DossierFundamentalsOut,
    DossierMarketDataOut,
    DossierPricePointOut,
    InstitutionalDisclosureOut,
    ReportedOwnershipCategoryOut,
    ReportedOwnershipOut,
    ShortActivityOut,
)
from api.institutional_research.universe import apply_research_product_scope
from bulls.analytics.research_conditions import build_condition_workbench
from bulls.core.markets import get_market_profile
from bulls.core.models import (
    DailyBar,
    InstitutionalHoldingSummary,
    MarketSummary,
    ShareholdingSnapshot,
    ShortVolumeDaily,
    Symbol,
    TickerAnalytics,
)
from bulls.core.symbol_lifecycle import PRIVATE_RESEARCH_STATUSES


class ResearchSecurityNotFound(LookupError):
    """The security is absent or is not eligible for tenant-bound research."""


def _reported_ownership(rows: list[ShareholdingSnapshot]) -> ReportedOwnershipOut | None:
    if not rows:
        return None
    latest = rows[0]
    previous = rows[1] if len(rows) > 1 else None
    definitions = (
        ("sponsor_director", "Sponsor / director", "sponsor_director"),
        ("government", "Government", "govt"),
        ("institutional", "Institutional", "institute"),
        ("foreign", "Foreign", "foreign_pct"),
        ("public", "Public", "public"),
    )

    def value(row: ShareholdingSnapshot, field: str) -> float:
        raw = getattr(row, field)
        return round(float(raw if raw is not None else 0.0), 4)

    categories = [
        ReportedOwnershipCategoryOut(
            key=key,
            label=label,
            value_pct=value(latest, field),
            change_pp=(
                round(value(latest, field) - value(previous, field), 4)
                if previous is not None
                else None
            ),
        )
        for key, label, field in definitions
    ]
    total = round(sum(item.value_pct for item in categories), 4)
    return ReportedOwnershipOut(
        as_of_date=latest.as_of_date,
        previous_as_of_date=previous.as_of_date if previous else None,
        composition_total_pct=total,
        categories=categories,
        interpretation=(
            "This is the issuer's reported ownership composition. Percentage-point changes "
            "describe differences between disclosures; they do not prove buying or selling "
            "during a specific trading session."
        ),
        limitations=[
            "Disclosure categories are reported at periodic dates, not observed in real time.",
            "Institutional and foreign categories do not identify individual investors.",
            "Reported public ownership is not the exchange-adjusted free float.",
        ],
    )


def _institutional_disclosure(
    row: InstitutionalHoldingSummary | None,
) -> InstitutionalDisclosureOut | None:
    if row is None:
        return None
    adding = row.new_positions + row.increased_positions
    reducing = row.reduced_positions + row.exited_positions
    changed = adding + reducing
    breadth = ((adding - reducing) / changed * 100.0) if changed else None
    return InstitutionalDisclosureOut(
        report_date=row.report_date,
        public_by=row.latest_filing_date,
        managers_count=row.managers_count,
        total_value_usd=row.total_value_usd,
        net_share_change=row.net_share_change,
        net_change_pct=row.net_change_pct,
        adding_managers=adding,
        reducing_managers=reducing,
        unchanged_managers=row.unchanged_positions,
        net_breadth_pct=round(breadth, 2) if breadth is not None else None,
        source_url=row.source_url,
        interpretation=(
            "Net breadth compares managers reporting new or increased positions with managers "
            "reporting reductions or exits for the quarter. It is evidence for investigation, "
            "not a live fund-flow or trade-direction signal."
        ),
        limitations=[
            "Form 13F reports quarter-end positions and can be filed up to 45 days later.",
            "The disclosure omits many shorts, derivatives, non-US securities, and intra-quarter trades.",
            "Aggregates can change because manager coverage or security-identifier mapping changed.",
        ],
    )


def _short_ratio(row: ShortVolumeDaily) -> float:
    total = float(row.total_volume)
    return float(row.short_volume) / total if total > 0 else 0.0


def _short_activity(rows: list[ShortVolumeDaily]) -> ShortActivityOut | None:
    if not rows:
        return None
    latest = rows[0]
    baseline = rows[1:21]
    ratio = _short_ratio(latest)
    baseline_ratios = [_short_ratio(row) for row in baseline]
    average = statistics.fmean(baseline_ratios) if baseline_ratios else None
    average_volume = (
        statistics.fmean(float(row.total_volume) for row in baseline) if baseline else None
    )
    activity_multiple = float(latest.total_volume) / average_volume if average_volume else None
    deviation = ratio - average if average is not None else None
    return ShortActivityOut(
        as_of_date=latest.date,
        short_marked_share_pct=round(ratio * 100.0, 2),
        average_20_pct=round(average * 100.0, 2) if average is not None else None,
        deviation_pp=round(deviation * 100.0, 2) if deviation is not None else None,
        activity_vs_20x=round(activity_multiple, 2) if activity_multiple is not None else None,
        baseline_sessions=len(baseline),
        source_url=f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{latest.date:%Y%m%d}.txt",
        interpretation=(
            "This compares FINRA-reported short-marked volume with the security's own recent "
            "baseline. It describes trading mechanics and cannot establish bearish positioning."
        ),
        limitations=[
            "FINRA daily files cover trades reported to FINRA facilities, not every US venue.",
            "Daily short-sale volume is not short interest and includes liquidity provision and hedging.",
            "The data does not show whether a short position remained open after the trade.",
        ],
    )


def _adjusted_ohlc(row: DailyBar) -> tuple[float, float, float, float]:
    """Apply the close adjustment ratio consistently across the complete bar."""

    close = float(row.close)
    adjusted_close = float(row.adjusted_close) if row.adjusted_close is not None else close
    adjustment = adjusted_close / close if close > 0 else 1.0
    return (
        float(row.open) * adjustment,
        float(row.high) * adjustment,
        float(row.low) * adjustment,
        adjusted_close,
    )


def _condition_workbench(
    rows: list[DossierPricePointOut],
) -> DossierConditionWorkbenchOut:
    """Serialize one shared analytics result into the public dossier contract."""

    return DossierConditionWorkbenchOut.model_validate(asdict(build_condition_workbench(rows)))


async def _price_history(
    session: AsyncSession,
    *,
    market: str,
    code: str,
    cutoff: dt.date,
) -> list[DossierPricePointOut]:
    rows = list(
        await session.scalars(
            select(DailyBar)
            .where(
                DailyBar.market == market,
                DailyBar.code == code,
                DailyBar.date <= cutoff,
            )
            .order_by(DailyBar.date.desc())
            .limit(252)
        )
    )
    if not rows:
        return []

    ordered_rows = list(reversed(rows))
    benchmark_rows = list(
        (
            await session.execute(
                select(
                    MarketSummary.date,
                    MarketSummary.benchmark_close,
                    MarketSummary.dsex,
                ).where(
                    MarketSummary.market == market,
                    MarketSummary.date >= ordered_rows[0].date,
                    MarketSummary.date <= ordered_rows[-1].date,
                )
            )
        ).all()
    )
    benchmark_by_date = {
        date: float(benchmark_close if benchmark_close is not None else dsex)
        for date, benchmark_close, dsex in benchmark_rows
        if benchmark_close is not None or dsex is not None
    }

    points: list[DossierPricePointOut] = []
    for row in ordered_rows:
        open_price, high, low, close = _adjusted_ohlc(row)
        points.append(
            DossierPricePointOut(
                date=row.date,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=int(row.volume),
                benchmark_close=benchmark_by_date.get(row.date),
            )
        )
    return points


async def build_company_dossier(
    session: AsyncSession,
    *,
    tenant_id: str,
    market: str,
    workspace_id: uuid.UUID,
    code: str,
) -> CompanyDossierOut:
    """Compose one point-in-time dossier without crossing the authenticated market boundary."""

    normalized_code = code.strip().upper()
    statement = (
        select(Symbol, TickerAnalytics)
        .join(
            TickerAnalytics,
            (TickerAnalytics.market == Symbol.market) & (TickerAnalytics.code == Symbol.code),
        )
        .where(
            Symbol.market == market,
            Symbol.code == normalized_code,
            TickerAnalytics.market == market,
            TickerAnalytics.code == normalized_code,
            Symbol.is_active.is_(True),
            Symbol.is_hidden.is_(False),
            Symbol.research_status.in_(PRIVATE_RESEARCH_STATUSES),
        )
    )
    row = (
        await session.execute(apply_research_product_scope(statement, market=market))
    ).one_or_none()
    if row is None:
        raise ResearchSecurityNotFound

    symbol, analytics = row
    cutoff = analytics.as_of_date
    price_history = await _price_history(
        session,
        market=market,
        code=normalized_code,
        cutoff=cutoff,
    )
    evidence = (await EVIDENCE_ADAPTERS[market].load(session, [normalized_code], cutoff=cutoff))[
        normalized_code
    ]
    candidate = _candidate(
        symbol=symbol,
        analytics=analytics,
        evidence=evidence,
        path=[point.close for point in price_history[-12:]],
        cutoff=cutoff,
    )

    reported_ownership = None
    institutional_disclosure = None
    short_activity = None
    if market == "DSE":
        ownership_rows = list(
            await session.scalars(
                select(ShareholdingSnapshot)
                .where(
                    ShareholdingSnapshot.market == market,
                    ShareholdingSnapshot.code == normalized_code,
                    ShareholdingSnapshot.as_of_date <= cutoff,
                    ShareholdingSnapshot.first_seen_at.isnot(None),
                    func.date(ShareholdingSnapshot.first_seen_at) <= cutoff,
                )
                .order_by(ShareholdingSnapshot.as_of_date.desc())
                .limit(2)
            )
        )
        reported_ownership = _reported_ownership(ownership_rows)
    elif market == "US":
        institutional_disclosure = _institutional_disclosure(
            await session.scalar(
                select(InstitutionalHoldingSummary)
                .where(
                    InstitutionalHoldingSummary.market == market,
                    InstitutionalHoldingSummary.code == normalized_code,
                    InstitutionalHoldingSummary.latest_filing_date <= cutoff,
                )
                .order_by(InstitutionalHoldingSummary.report_date.desc())
                .limit(1)
            )
        )
        short_rows = list(
            await session.scalars(
                select(ShortVolumeDaily)
                .where(
                    ShortVolumeDaily.market == market,
                    ShortVolumeDaily.code == normalized_code,
                    ShortVolumeDaily.date <= cutoff,
                )
                .order_by(ShortVolumeDaily.date.desc())
                .limit(21)
            )
        )
        short_activity = _short_activity(short_rows)

    data_quality_notes: list[str] = []
    if len(price_history) < 200:
        data_quality_notes.append(
            f"Only {len(price_history)} completed sessions are available; long-horizon conclusions are limited."
        )
    if candidate.evidence.coverage_pct < 100:
        missing = [item.label for item in candidate.evidence.requirements if not item.present]
        data_quality_notes.append("Missing required evidence: " + ", ".join(missing) + ".")
    if market == "DSE" and reported_ownership is None:
        data_quality_notes.append(
            "No validated DSE ownership disclosure is available at the cutoff."
        )
    if market == "US" and institutional_disclosure is None:
        data_quality_notes.append("No matched quarterly 13F aggregate is available at the cutoff.")
    if market == "US" and short_activity is None:
        data_quality_notes.append(
            "No matched FINRA daily short-volume record is available at the cutoff."
        )

    return CompanyDossierOut(
        tenant_id=tenant_id,
        market=market,
        workspace_id=workspace_id,
        generated_at=dt.datetime.now(dt.UTC),
        knowledge_cutoff_at=_as_utc(analytics.computed_at),
        candidate=candidate,
        market_data=DossierMarketDataOut(
            as_of_date=cutoff,
            benchmark_code=get_market_profile(market).benchmark_code,
            market_cap_mn=analytics.market_cap_mn,
            free_float_cap_mn=analytics.free_float_cap_mn,
            week52_high=analytics.week52_high,
            week52_low=analytics.week52_low,
            nearest_support=analytics.nearest_support,
            nearest_resistance=analytics.nearest_resistance,
            average_volume_20=analytics.avg_volume_20,
            relative_volume=analytics.relative_volume,
            cmf_20=analytics.cmf_20,
            obv_slope=analytics.obv_slope,
            rsi_14=analytics.rsi_14,
            volatility_pct=analytics.volatility,
        ),
        fundamentals=DossierFundamentalsOut(
            pe_ratio=analytics.pe_ratio,
            pb_ratio=analytics.pb_ratio,
            dividend_yield_pct=analytics.dividend_yield,
            roe_pct=analytics.roe,
            eps_growth_yoy_pct=analytics.eps_growth_yoy,
            pe_vs_sector=analytics.pe_vs_sector,
        ),
        price_history=price_history,
        condition_workbench=_condition_workbench(price_history),
        reported_ownership=reported_ownership,
        institutional_disclosure=institutional_disclosure,
        short_activity=short_activity,
        data_quality_notes=data_quality_notes,
    )
