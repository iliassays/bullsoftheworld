"""Deterministic, auditable security-onboarding quality gates."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import case, func, select

from bulls.core.db import get_sessionmaker
from bulls.core.models import (
    DailyBar,
    InstitutionalHoldingSummary,
    SecFiling,
    SecFinancialFact,
    SecurityMaster,
    Symbol,
    TickerAnalytics,
)
from ingestion.cohorts import OnboardingPolicy


@dataclass(frozen=True)
class GateEvidence:
    code: str
    security_id: uuid.UUID | None
    passed: bool
    gates: dict[str, dict[str, Any]]
    failure_reasons: list[str]
    bar_count: int
    first_bar_date: dt.date | None
    last_bar_date: dt.date | None
    adjusted_close_ratio: float | None
    nonzero_volume_ratio: float | None
    sec_filings_count: int
    sec_facts_count: int
    has_13f: bool

    def result_row(self, run_id: uuid.UUID, market: str, now: dt.datetime) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "market": market,
            "code": self.code,
            "security_id": self.security_id,
            "decision": "passed" if self.passed else "failed",
            "required_gates_passed": self.passed,
            "gates": self.gates,
            "failure_reasons": self.failure_reasons,
            "bar_count": self.bar_count,
            "first_bar_date": self.first_bar_date,
            "last_bar_date": self.last_bar_date,
            "adjusted_close_ratio": self.adjusted_close_ratio,
            "nonzero_volume_ratio": self.nonzero_volume_ratio,
            "sec_filings_count": self.sec_filings_count,
            "sec_facts_count": self.sec_facts_count,
            "has_13f": self.has_13f,
            "evaluated_at": now,
        }


def _gate(
    passed: bool,
    *,
    required: bool = True,
    actual: Any = None,
    expected: Any = None,
) -> dict[str, Any]:
    return {
        "passed": bool(passed),
        "required": required,
        "actual": actual,
        "expected": expected,
    }


def _evaluate_symbol(
    *,
    code: str,
    symbol: Symbol | None,
    security: SecurityMaster | None,
    bars: tuple[int, dt.date | None, dt.date | None, int, int, int] | None,
    sec_filings: int,
    sec_facts: int,
    has_analytics: bool,
    has_13f: bool,
    policy: OnboardingPolicy,
    as_of_date: dt.date,
    analytics_snapshot: tuple[float | None, float | None, float | None] | None = None,
) -> GateEvidence:
    bar_count, first_date, last_date, adjusted_count, volume_count, invalid_ohlc = bars or (
        0,
        None,
        None,
        0,
        0,
        0,
    )
    adjusted_ratio = adjusted_count / bar_count if bar_count else None
    volume_ratio = volume_count / bar_count if bar_count else None
    instrument_type = security.instrument_type if security else None
    cik_required = instrument_type in policy.require_cik_for
    filings_required = instrument_type in policy.sec_filings_required_for
    facts_required = instrument_type in policy.sec_facts_required_for
    stale_days = (as_of_date - last_date).days if last_date else None
    history_days = (last_date - first_date).days if first_date and last_date else 0
    last_close, avg_volume_20, market_cap_mn = analytics_snapshot or (None, None, None)
    adtv_mn = (
        last_close * avg_volume_20 / 1e6
        if last_close is not None and avg_volume_20 is not None
        else None
    )

    gates = {
        "symbol": _gate(symbol is not None, actual=bool(symbol), expected=True),
        "stable_identity": _gate(
            bool(security and security.security_id and symbol and symbol.security_id == security.security_id),
            actual=str(symbol.security_id) if symbol and symbol.security_id else None,
            expected=str(security.security_id) if security else "security_master UUID",
        ),
        "product_eligible": _gate(
            bool(security and security.is_active and security.is_product_eligible),
            actual=security.exclude_reason if security else "missing",
            expected="active eligible listing",
        ),
        "instrument_type": _gate(
            instrument_type in policy.allowed_instrument_types,
            actual=instrument_type,
            expected=list(policy.allowed_instrument_types),
        ),
        "exchange": _gate(
            bool(security and security.exchange),
            actual=security.exchange if security else None,
            expected="known exchange",
        ),
        "bar_depth": _gate(
            bar_count >= policy.min_bars,
            actual=bar_count,
            expected=f">={policy.min_bars}",
        ),
        "history_span": _gate(
            history_days >= policy.min_history_days,
            actual=history_days,
            expected=f">={policy.min_history_days} days",
        ),
        "freshness": _gate(
            stale_days is not None and 0 <= stale_days <= policy.max_staleness_days,
            actual=stale_days,
            expected=f"0..{policy.max_staleness_days} days",
        ),
        "adjusted_close": _gate(
            adjusted_ratio is not None and adjusted_ratio >= policy.min_adjusted_close_ratio,
            actual=round(adjusted_ratio, 4) if adjusted_ratio is not None else None,
            expected=f">={policy.min_adjusted_close_ratio}",
        ),
        "nonzero_volume": _gate(
            volume_ratio is not None and volume_ratio >= policy.min_nonzero_volume_ratio,
            actual=round(volume_ratio, 4) if volume_ratio is not None else None,
            expected=f">={policy.min_nonzero_volume_ratio}",
        ),
        "ohlc_integrity": _gate(invalid_ohlc == 0, actual=invalid_ohlc, expected=0),
        "cik": _gate(
            bool(security and security.cik),
            required=cik_required,
            actual=security.cik if security else None,
            expected="CIK" if cik_required else "not required",
        ),
        "sec_filings": _gate(
            sec_filings >= policy.min_sec_filings,
            required=filings_required,
            actual=sec_filings,
            expected=f">={policy.min_sec_filings}" if filings_required else "not required",
        ),
        "sec_facts": _gate(
            sec_facts >= policy.min_sec_facts,
            required=facts_required,
            actual=sec_facts,
            expected=f">={policy.min_sec_facts}" if facts_required else "not required",
        ),
        "analytics": _gate(
            has_analytics if policy.require_analytics else True,
            required=policy.require_analytics,
            actual=has_analytics,
            expected=True if policy.require_analytics else "not required",
        ),
        "market_cap_floor": _gate(
            market_cap_mn is not None and market_cap_mn >= policy.min_market_cap_mn
            if policy.min_market_cap_mn is not None
            else True,
            required=policy.min_market_cap_mn is not None,
            actual=round(market_cap_mn, 2) if market_cap_mn is not None else None,
            expected=(f">={policy.min_market_cap_mn} USD mn" if policy.min_market_cap_mn else "not required"),
        ),
        "market_cap_ceiling": _gate(
            market_cap_mn is not None and market_cap_mn <= policy.max_market_cap_mn
            if policy.max_market_cap_mn is not None
            else True,
            required=policy.max_market_cap_mn is not None,
            actual=round(market_cap_mn, 2) if market_cap_mn is not None else None,
            expected=(f"<={policy.max_market_cap_mn} USD mn" if policy.max_market_cap_mn else "not required"),
        ),
        "liquidity": _gate(
            adtv_mn is not None and adtv_mn >= policy.min_adtv_mn
            if policy.min_adtv_mn is not None
            else True,
            required=policy.min_adtv_mn is not None,
            actual=round(adtv_mn, 2) if adtv_mn is not None else None,
            expected=f">={policy.min_adtv_mn} USD mn ADTV" if policy.min_adtv_mn else "not required",
        ),
        "price_floor": _gate(
            last_close is not None and last_close >= policy.min_price
            if policy.min_price is not None
            else True,
            required=policy.min_price is not None,
            actual=round(last_close, 4) if last_close is not None else None,
            expected=f">={policy.min_price} USD" if policy.min_price else "not required",
        ),
        "institutional_mapping": _gate(
            has_13f,
            required=policy.require_13f,
            actual=has_13f,
            expected=True if policy.require_13f else "informational",
        ),
    }
    failures = [name for name, value in gates.items() if value["required"] and not value["passed"]]
    return GateEvidence(
        code=code,
        security_id=security.security_id if security else None,
        passed=not failures,
        gates=gates,
        failure_reasons=failures,
        bar_count=bar_count,
        first_bar_date=first_date,
        last_bar_date=last_date,
        adjusted_close_ratio=round(adjusted_ratio, 6) if adjusted_ratio is not None else None,
        nonzero_volume_ratio=round(volume_ratio, 6) if volume_ratio is not None else None,
        sec_filings_count=sec_filings,
        sec_facts_count=sec_facts,
        has_13f=has_13f,
    )


async def evaluate_cohort(
    market: str,
    codes: tuple[str, ...],
    policy: OnboardingPolicy,
    *,
    as_of_date: dt.date,
) -> list[GateEvidence]:
    sm = get_sessionmaker()
    async with sm() as session:
        symbols = {
            row.code: row
            for row in await session.scalars(
                select(Symbol).where(Symbol.market == market, Symbol.code.in_(codes))
            )
        }
        securities = {
            row.symbol: row
            for row in await session.scalars(
                select(SecurityMaster).where(
                    SecurityMaster.market == market,
                    SecurityMaster.symbol.in_(codes),
                )
            )
        }
        bar_rows = (
            await session.execute(
                select(
                    DailyBar.code,
                    func.count(),
                    func.min(DailyBar.date),
                    func.max(DailyBar.date),
                    func.sum(case((DailyBar.adjusted_close.isnot(None), 1), else_=0)),
                    func.sum(case((DailyBar.volume > 0, 1), else_=0)),
                    func.sum(
                        case(
                            (
                                (DailyBar.open <= 0)
                                | (DailyBar.high <= 0)
                                | (DailyBar.low <= 0)
                                | (DailyBar.close <= 0)
                                | (DailyBar.high < DailyBar.low)
                                | (DailyBar.high < DailyBar.open)
                                | (DailyBar.high < DailyBar.close)
                                | (DailyBar.low > DailyBar.open)
                                | (DailyBar.low > DailyBar.close),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                )
                .where(DailyBar.market == market, DailyBar.code.in_(codes))
                .group_by(DailyBar.code)
            )
        ).all()
        bars = {
            code: (
                int(count),
                first_date,
                last_date,
                int(adjusted_count or 0),
                int(volume_count or 0),
                int(invalid_count or 0),
            )
            for code, count, first_date, last_date, adjusted_count, volume_count, invalid_count in bar_rows
        }
        filing_counts = dict(
            (
                await session.execute(
                    select(SecFiling.code, func.count())
                    .where(SecFiling.market == market, SecFiling.code.in_(codes))
                    .group_by(SecFiling.code)
                )
            ).all()
        )
        fact_counts = dict(
            (
                await session.execute(
                    select(SecFinancialFact.code, func.count())
                    .where(SecFinancialFact.market == market, SecFinancialFact.code.in_(codes))
                    .group_by(SecFinancialFact.code)
                )
            ).all()
        )
        analytics = {
            code: (last_close, avg_volume_20, market_cap_mn)
            for code, last_close, avg_volume_20, market_cap_mn in (
                await session.execute(
                    select(
                        TickerAnalytics.code,
                        TickerAnalytics.last_close,
                        TickerAnalytics.avg_volume_20,
                        TickerAnalytics.market_cap_mn,
                    ).where(
                    TickerAnalytics.market == market,
                    TickerAnalytics.code.in_(codes),
                )
                )
            ).all()
        }
        holdings = set(
            await session.scalars(
                select(InstitutionalHoldingSummary.code)
                .where(
                    InstitutionalHoldingSummary.market == market,
                    InstitutionalHoldingSummary.code.in_(codes),
                )
                .distinct()
            )
        )

    return [
        _evaluate_symbol(
            code=code,
            symbol=symbols.get(code),
            security=securities.get(code),
            bars=bars.get(code),
            sec_filings=int(filing_counts.get(code, 0)),
            sec_facts=int(fact_counts.get(code, 0)),
            has_analytics=code in analytics,
            analytics_snapshot=analytics.get(code),
            has_13f=code in holdings,
            policy=policy,
            as_of_date=as_of_date,
        )
        for code in codes
    ]
