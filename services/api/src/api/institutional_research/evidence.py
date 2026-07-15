from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bulls.core.models import (
    Announcement,
    InstitutionalHoldingSummary,
    SecFiling,
    SecFinancialFact,
    ShortVolumeDaily,
    TickerAnalytics,
)


@dataclass(frozen=True, slots=True)
class EvidenceRequirement:
    key: str
    label: str
    present: bool
    as_of: dt.date | None


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    id: str
    source: str
    title: str
    published_at: dt.date
    url: str | None


@dataclass(slots=True)
class EvidenceBundle:
    official_count: int = 0
    latest_official_date: dt.date | None = None
    requirements: list[EvidenceRequirement] = field(default_factory=list)
    items: list[EvidenceItem] = field(default_factory=list)


class MarketEvidenceAdapter(Protocol):
    async def load(
        self,
        session: AsyncSession,
        codes: list[str],
        *,
        cutoff: dt.date,
    ) -> dict[str, EvidenceBundle]: ...

    def analytics_requirements(self, row: TickerAnalytics) -> list[EvidenceRequirement]: ...


def _present_date(value: dt.date | None) -> bool:
    return value is not None


class DseEvidenceAdapter:
    async def load(
        self,
        session: AsyncSession,
        codes: list[str],
        *,
        cutoff: dt.date,
    ) -> dict[str, EvidenceBundle]:
        bundles = {code: EvidenceBundle() for code in codes}
        if not codes:
            return bundles

        ranked = (
            select(
                Announcement.id.label("id"),
                Announcement.code.label("code"),
                Announcement.headline.label("title"),
                Announcement.published_at.label("published_at"),
                func.count().over(partition_by=Announcement.code).label("source_count"),
                func.row_number()
                .over(
                    partition_by=Announcement.code,
                    order_by=(Announcement.published_at.desc(), Announcement.strength.desc()),
                )
                .label("rank"),
            )
            .where(
                Announcement.market == "DSE",
                Announcement.code.in_(codes),
                Announcement.published_at <= cutoff,
                Announcement.published_at >= cutoff - dt.timedelta(days=365),
            )
            .subquery()
        )
        rows = (
            await session.execute(
                select(ranked).where(ranked.c.rank <= 3).order_by(ranked.c.code, ranked.c.rank)
            )
        ).mappings()
        for row in rows:
            bundle = bundles[row["code"]]
            bundle.official_count = int(row["source_count"])
            if bundle.latest_official_date is None:
                bundle.latest_official_date = row["published_at"]
            bundle.items.append(
                EvidenceItem(
                    id=f"dse:{row['id']}",
                    source="DSE",
                    title=row["title"],
                    published_at=row["published_at"],
                    url=None,
                )
            )
        for bundle in bundles.values():
            bundle.requirements.append(
                EvidenceRequirement(
                    key="official_disclosures",
                    label="Official DSE disclosures",
                    present=_present_date(bundle.latest_official_date),
                    as_of=bundle.latest_official_date,
                )
            )
        return bundles

    def analytics_requirements(self, row: TickerAnalytics) -> list[EvidenceRequirement]:
        fundamentals = any(
            value is not None for value in (row.pe_ratio, row.pb_ratio, row.roe, row.eps_growth_yoy)
        )
        ownership = any(
            value is not None
            for value in (row.sponsor_pct, row.institute_pct, row.foreign_pct, row.public_pct)
        )
        return [
            EvidenceRequirement("market_data", "EOD market analytics", True, row.as_of_date),
            EvidenceRequirement(
                "fundamentals", "Company fundamentals", fundamentals, row.as_of_date
            ),
            EvidenceRequirement("ownership", "Reported ownership", ownership, row.as_of_date),
        ]


class UsEvidenceAdapter:
    async def load(
        self,
        session: AsyncSession,
        codes: list[str],
        *,
        cutoff: dt.date,
    ) -> dict[str, EvidenceBundle]:
        bundles = {code: EvidenceBundle() for code in codes}
        if not codes:
            return bundles

        ranked = (
            select(
                SecFiling.accession_number.label("id"),
                SecFiling.code.label("code"),
                SecFiling.form.label("form"),
                SecFiling.description.label("description"),
                SecFiling.filing_date.label("published_at"),
                SecFiling.filing_url.label("url"),
                func.count().over(partition_by=SecFiling.code).label("source_count"),
                func.row_number()
                .over(
                    partition_by=SecFiling.code,
                    order_by=(SecFiling.filing_date.desc(), SecFiling.accession_number.desc()),
                )
                .label("rank"),
            )
            .where(
                SecFiling.market == "US",
                SecFiling.code.in_(codes),
                SecFiling.filing_date <= cutoff,
                SecFiling.filing_date >= cutoff - dt.timedelta(days=365),
            )
            .subquery()
        )
        rows = (
            await session.execute(
                select(ranked).where(ranked.c.rank <= 3).order_by(ranked.c.code, ranked.c.rank)
            )
        ).mappings()
        for row in rows:
            bundle = bundles[row["code"]]
            bundle.official_count = int(row["source_count"])
            if bundle.latest_official_date is None:
                bundle.latest_official_date = row["published_at"]
            description = (row["description"] or "").strip()
            title = f"{row['form']} filing" + (f": {description}" if description else "")
            bundle.items.append(
                EvidenceItem(
                    id=f"sec:{row['id']}",
                    source="SEC EDGAR",
                    title=title,
                    published_at=row["published_at"],
                    url=row["url"],
                )
            )

        requirement_queries = {
            "company_facts": (
                "SEC Company Facts",
                select(SecFinancialFact.code, func.max(SecFinancialFact.filed_at))
                .where(
                    SecFinancialFact.market == "US",
                    SecFinancialFact.code.in_(codes),
                    SecFinancialFact.filed_at <= cutoff,
                )
                .group_by(SecFinancialFact.code),
            ),
            "institutional_holdings": (
                "Reported institutional holdings",
                select(
                    InstitutionalHoldingSummary.code,
                    func.max(InstitutionalHoldingSummary.latest_filing_date),
                )
                .where(
                    InstitutionalHoldingSummary.market == "US",
                    InstitutionalHoldingSummary.code.in_(codes),
                    InstitutionalHoldingSummary.latest_filing_date <= cutoff,
                )
                .group_by(InstitutionalHoldingSummary.code),
            ),
            "finra_short_volume": (
                "FINRA daily short volume",
                select(ShortVolumeDaily.code, func.max(ShortVolumeDaily.date))
                .where(
                    ShortVolumeDaily.market == "US",
                    ShortVolumeDaily.code.in_(codes),
                    ShortVolumeDaily.date <= cutoff,
                )
                .group_by(ShortVolumeDaily.code),
            ),
        }
        requirement_dates: dict[str, dict[str, dt.date]] = {}
        for key, (_, statement) in requirement_queries.items():
            requirement_dates[key] = {code: date for code, date in await session.execute(statement)}

        for code, bundle in bundles.items():
            bundle.requirements.append(
                EvidenceRequirement(
                    "sec_filings",
                    "SEC filings",
                    _present_date(bundle.latest_official_date),
                    bundle.latest_official_date,
                )
            )
            for key, (label, _) in requirement_queries.items():
                as_of = requirement_dates[key].get(code)
                bundle.requirements.append(
                    EvidenceRequirement(key, label, _present_date(as_of), as_of)
                )
        return bundles

    def analytics_requirements(self, row: TickerAnalytics) -> list[EvidenceRequirement]:
        fundamentals = any(
            value is not None for value in (row.pe_ratio, row.pb_ratio, row.roe, row.eps_growth_yoy)
        )
        return [
            EvidenceRequirement("market_data", "EOD market analytics", True, row.as_of_date),
            EvidenceRequirement(
                "fundamentals", "Normalized fundamentals", fundamentals, row.as_of_date
            ),
        ]


EVIDENCE_ADAPTERS: dict[str, MarketEvidenceAdapter] = {
    "DSE": DseEvidenceAdapter(),
    "US": UsEvidenceAdapter(),
}
