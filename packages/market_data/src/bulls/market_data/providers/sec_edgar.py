"""Official SEC EDGAR submissions and Company Facts client.

The transport payloads are intentionally normalized here before ingestion sees them. Only selected
decision-useful XBRL concepts survive, and amendments replace older values for the same period.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel

DATA_BASE = "https://data.sec.gov"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
ALLOWED_FORMS = frozenset(
    {
        "10-K",
        "10-K/A",
        "10-Q",
        "10-Q/A",
        "8-K",
        "8-K/A",
        "20-F",
        "20-F/A",
        "40-F",
        "40-F/A",
        "6-K",
        "6-K/A",
        "DEF 14A",
        "3",
        "3/A",
        "4",
        "4/A",
        "5",
        "5/A",
        "S-1",
        "S-1/A",
        "SC 13D",
        "SC 13D/A",
        "SC 13G",
        "SC 13G/A",
    }
)
ANNUAL_FORMS = frozenset({"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"})
QUARTERLY_FORMS = frozenset({"10-Q", "10-Q/A"})
MAX_FACT_PERIODS = 24
FACT_RETENTION_YEARS = 8
FILING_RETENTION_YEARS = 7
ADDITIVE_YTD_METRICS = frozenset(
    {
        "revenue",
        "gross_profit",
        "operating_income",
        "net_income",
        "operating_cash_flow",
        "capital_expenditure",
        "dividends_per_share",
        "share_repurchases",
    }
)


class SecIssuerProfile(BaseModel):
    cik: int
    name: str
    sic: str | None = None
    sic_description: str | None = None
    fiscal_year_end: str | None = None
    state_of_incorporation: str | None = None


class SecFilingRecord(BaseModel):
    market: str = "US"
    code: str
    cik: int
    accession_number: str
    form: str
    category: str
    filing_date: dt.date
    report_date: dt.date | None = None
    accepted_at: dt.datetime | None = None
    primary_document: str
    description: str | None = None
    items: str | None = None
    is_xbrl: bool = False
    is_inline_xbrl: bool = False
    filing_url: str
    source_updated_at: dt.datetime


class SecFinancialFactRecord(BaseModel):
    market: str = "US"
    code: str
    metric: str
    value: float
    unit: str
    period_start: dt.date | None = None
    period_end: dt.date
    period_type: str
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    form: str
    filed_at: dt.date
    accession_number: str
    taxonomy: str
    source_concept: str
    frame: str | None = None
    source_url: str


@dataclass(frozen=True)
class FactConcept:
    taxonomy: str
    concept: str
    units: tuple[str, ...]


@dataclass(frozen=True)
class MetricSpec:
    metric: str
    instant: bool
    concepts: tuple[FactConcept, ...]


def _c(taxonomy: str, concept: str, *units: str) -> FactConcept:
    return FactConcept(taxonomy, concept, tuple(units))


METRIC_SPECS: tuple[MetricSpec, ...] = (
    MetricSpec(
        "revenue",
        False,
        (
            _c("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "USD"),
            _c("us-gaap", "Revenues", "USD"),
            _c("us-gaap", "SalesRevenueNet", "USD"),
            _c("ifrs-full", "Revenue", "USD"),
        ),
    ),
    MetricSpec(
        "gross_profit",
        False,
        (_c("us-gaap", "GrossProfit", "USD"), _c("ifrs-full", "GrossProfit", "USD")),
    ),
    MetricSpec(
        "operating_income",
        False,
        (
            _c("us-gaap", "OperatingIncomeLoss", "USD"),
            _c("ifrs-full", "ProfitLossFromOperatingActivities", "USD"),
        ),
    ),
    MetricSpec(
        "net_income",
        False,
        (
            _c("us-gaap", "NetIncomeLoss", "USD"),
            _c("us-gaap", "ProfitLoss", "USD"),
            _c("ifrs-full", "ProfitLoss", "USD"),
        ),
    ),
    MetricSpec(
        "eps_diluted",
        False,
        (
            _c("us-gaap", "EarningsPerShareDiluted", "USD/shares", "USD / shares"),
            _c("ifrs-full", "DilutedEarningsLossPerShare", "USD/shares", "USD / shares"),
        ),
    ),
    MetricSpec(
        "eps_basic",
        False,
        (
            _c("us-gaap", "EarningsPerShareBasic", "USD/shares", "USD / shares"),
            _c("ifrs-full", "BasicEarningsLossPerShare", "USD/shares", "USD / shares"),
        ),
    ),
    MetricSpec("assets", True, (_c("us-gaap", "Assets", "USD"), _c("ifrs-full", "Assets", "USD"))),
    MetricSpec(
        "current_assets",
        True,
        (_c("us-gaap", "AssetsCurrent", "USD"), _c("ifrs-full", "CurrentAssets", "USD")),
    ),
    MetricSpec(
        "liabilities",
        True,
        (_c("us-gaap", "Liabilities", "USD"), _c("ifrs-full", "Liabilities", "USD")),
    ),
    MetricSpec(
        "current_liabilities",
        True,
        (
            _c("us-gaap", "LiabilitiesCurrent", "USD"),
            _c("ifrs-full", "CurrentLiabilities", "USD"),
        ),
    ),
    MetricSpec(
        "equity",
        True,
        (
            _c("us-gaap", "StockholdersEquity", "USD"),
            _c(
                "us-gaap",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
                "USD",
            ),
            _c("ifrs-full", "Equity", "USD"),
        ),
    ),
    MetricSpec(
        "cash",
        True,
        (
            _c("us-gaap", "CashAndCashEquivalentsAtCarryingValue", "USD"),
            _c("ifrs-full", "CashAndCashEquivalents", "USD"),
        ),
    ),
    MetricSpec(
        "debt_current",
        True,
        (
            _c("us-gaap", "LongTermDebtCurrent", "USD"),
            _c("us-gaap", "ShortTermBorrowings", "USD"),
            _c("ifrs-full", "CurrentBorrowings", "USD"),
        ),
    ),
    MetricSpec(
        "debt_noncurrent",
        True,
        (
            _c("us-gaap", "LongTermDebtNoncurrent", "USD"),
            _c("ifrs-full", "NoncurrentBorrowings", "USD"),
        ),
    ),
    MetricSpec(
        "debt_total",
        True,
        (
            _c("us-gaap", "LongTermDebtAndFinanceLeaseObligations", "USD"),
            _c("us-gaap", "LongTermDebt", "USD"),
            _c("ifrs-full", "Borrowings", "USD"),
        ),
    ),
    MetricSpec(
        "shares_outstanding",
        True,
        (
            _c("dei", "EntityCommonStockSharesOutstanding", "shares"),
            _c("us-gaap", "CommonStockSharesOutstanding", "shares"),
        ),
    ),
    MetricSpec(
        "operating_cash_flow",
        False,
        (
            _c("us-gaap", "NetCashProvidedByUsedInOperatingActivities", "USD"),
            _c("ifrs-full", "CashFlowsFromUsedInOperatingActivities", "USD"),
        ),
    ),
    MetricSpec(
        "capital_expenditure",
        False,
        (
            _c("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment", "USD"),
            _c("ifrs-full", "PurchaseOfPropertyPlantAndEquipment", "USD"),
        ),
    ),
    MetricSpec(
        "dividends_per_share",
        False,
        (
            _c("us-gaap", "CommonStockDividendsPerShareDeclared", "USD/shares", "USD / shares"),
            _c("ifrs-full", "DividendsPaidPerShare", "USD/shares", "USD / shares"),
        ),
    ),
    MetricSpec(
        "share_repurchases",
        False,
        (_c("us-gaap", "PaymentsForRepurchaseOfCommonStock", "USD"),),
    ),
)


def _date(value: Any) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _datetime(value: Any) -> dt.datetime | None:
    if not value:
        return None
    raw = str(value).replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(raw)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.UTC)
    except ValueError:
        return None


def _truthy(value: Any) -> bool:
    return str(value or "").strip() in {"1", "true", "True", "Y"}


def years_ago(value: dt.date, years: int) -> dt.date:
    """Return a calendar-year cutoff, clamping leap day to February 28."""
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def filing_category(form: str, items: str | None = None, description: str | None = None) -> str:
    base = form.removesuffix("/A")
    if base in {"10-K", "20-F", "40-F"}:
        return "annual_report"
    if base == "10-Q":
        return "quarterly_report"
    if base == "6-K":
        text = (description or "").lower()
        return (
            "earnings"
            if any(word in text for word in ("results", "earnings"))
            else "foreign_report"
        )
    if base == "8-K":
        item_set = {part.strip() for part in (items or "").split(",")}
        if "2.02" in item_set:
            return "earnings"
        if "2.01" in item_set:
            return "acquisition"
        if "5.02" in item_set:
            return "leadership"
        return "current_report"
    if base == "DEF 14A":
        return "proxy"
    if base in {"3", "4", "5"}:
        return "insider_ownership"
    if base.startswith("SC 13"):
        return "beneficial_ownership"
    if base == "S-1":
        return "registration"
    return "filing"


def filing_index_url(cik: int, accession_number: str) -> str:
    compact = accession_number.replace("-", "")
    return f"{ARCHIVES_BASE}/{cik}/{compact}/{accession_number}-index.html"


def filing_document_url(cik: int, accession_number: str, primary_document: str) -> str:
    compact = accession_number.replace("-", "")
    return f"{ARCHIVES_BASE}/{cik}/{compact}/{primary_document}"


def _columnar_rows(recent: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
    keys = tuple(recent)
    columns = [recent.get(key) if isinstance(recent.get(key), list) else [] for key in keys]
    size = max((len(column) for column in columns), default=0)
    for index in range(size):
        yield {
            key: column[index] if index < len(column) else None
            for key, column in zip(keys, columns, strict=True)
        }


def parse_submissions(
    code: str,
    payload: Mapping[str, Any],
    *,
    fetched_at: dt.datetime | None = None,
    today: dt.date | None = None,
) -> tuple[SecIssuerProfile, list[SecFilingRecord]]:
    fetched_at = fetched_at or dt.datetime.now(dt.UTC)
    cutoff = years_ago(today or fetched_at.date(), FILING_RETENTION_YEARS)
    cik = int(payload["cik"])
    profile = SecIssuerProfile(
        cik=cik,
        name=str(payload.get("name") or code),
        sic=str(payload.get("sic") or "") or None,
        sic_description=str(payload.get("sicDescription") or "") or None,
        fiscal_year_end=str(payload.get("fiscalYearEnd") or "") or None,
        state_of_incorporation=str(payload.get("stateOfIncorporation") or "") or None,
    )
    recent = payload.get("filings", {}).get("recent", {})
    out: list[SecFilingRecord] = []
    for row in _columnar_rows(recent if isinstance(recent, Mapping) else {}):
        form = str(row.get("form") or "")
        filing_date = _date(row.get("filingDate"))
        accession = str(row.get("accessionNumber") or "")
        primary_document = str(row.get("primaryDocument") or "")
        if (
            form not in ALLOWED_FORMS
            or filing_date is None
            or filing_date < cutoff
            or not accession
            or not primary_document
        ):
            continue
        items = str(row.get("items") or "").strip() or None
        description = str(row.get("primaryDocDescription") or "").strip() or None
        out.append(
            SecFilingRecord(
                code=code,
                cik=cik,
                accession_number=accession,
                form=form,
                category=filing_category(form, items, description),
                filing_date=filing_date,
                report_date=_date(row.get("reportDate")),
                accepted_at=_datetime(row.get("acceptanceDateTime")),
                primary_document=primary_document,
                description=description,
                items=items,
                is_xbrl=_truthy(row.get("isXBRL")),
                is_inline_xbrl=_truthy(row.get("isInlineXBRL")),
                filing_url=filing_document_url(cik, accession, primary_document),
                source_updated_at=fetched_at,
            )
        )
    return profile, sorted(out, key=lambda row: row.filing_date, reverse=True)


def _period_type(spec: MetricSpec, form: str, start: dt.date | None, end: dt.date) -> str | None:
    if spec.instant:
        return "instant"
    if start is None:
        return None
    duration = (end - start).days
    if form in ANNUAL_FORMS and 250 <= duration <= 450:
        return "annual"
    if form in QUARTERLY_FORMS and 60 <= duration <= 150:
        return "quarter"
    if form in QUARTERLY_FORMS and 151 <= duration <= 310:
        return "ytd"
    return None


def _normalized_periods(
    rows: list[SecFinancialFactRecord], metric: str
) -> list[SecFinancialFactRecord]:
    """Convert adjacent cumulative 10-Q values to standalone quarters when mathematically valid."""
    quarters = {row.period_end: row for row in rows if row.period_type == "quarter"}
    if metric in ADDITIVE_YTD_METRICS:
        cumulative = sorted(
            (row for row in rows if row.period_type == "ytd"),
            key=lambda row: row.period_end,
        )
        bases = [row for row in rows if row.period_type in {"quarter", "ytd"}]
        for current in cumulative:
            if current.period_end in quarters or current.period_start is None:
                continue
            candidates = [
                prior
                for prior in bases
                if prior.period_start == current.period_start
                and prior.period_end < current.period_end
                and 60 <= (current.period_end - prior.period_end).days <= 150
            ]
            if not candidates:
                continue
            prior = max(candidates, key=lambda row: (row.period_end, row.filed_at))
            quarters[current.period_end] = current.model_copy(
                update={
                    "value": current.value - prior.value,
                    "period_start": prior.period_end + dt.timedelta(days=1),
                    "period_type": "quarter",
                    "frame": f"derived:{prior.period_end}",
                }
            )
    non_quarterly = [row for row in rows if row.period_type not in {"quarter", "ytd"}]
    return non_quarterly + list(quarters.values())


def parse_company_fact_observations(
    code: str,
    cik: int,
    payload: Mapping[str, Any],
    *,
    today: dt.date | None = None,
) -> list[SecFinancialFactRecord]:
    """Parse every retained accession-level fact before current-projection selection."""
    today = today or dt.datetime.now(dt.UTC).date()
    cutoff = years_ago(today, FACT_RETENTION_YEARS)
    facts = payload.get("facts", {})
    observations: list[SecFinancialFactRecord] = []

    for spec in METRIC_SPECS:
        for concept in spec.concepts:
            taxonomy = facts.get(concept.taxonomy, {}) if isinstance(facts, Mapping) else {}
            concept_payload = (
                taxonomy.get(concept.concept, {}) if isinstance(taxonomy, Mapping) else {}
            )
            units = concept_payload.get("units", {}) if isinstance(concept_payload, Mapping) else {}
            if not isinstance(units, Mapping):
                continue
            for unit in concept.units:
                entries = units.get(unit, [])
                if not isinstance(entries, list):
                    continue
                for raw in entries:
                    if not isinstance(raw, Mapping):
                        continue
                    end = _date(raw.get("end"))
                    start = _date(raw.get("start"))
                    filed = _date(raw.get("filed"))
                    form = str(raw.get("form") or "")
                    accession = str(raw.get("accn") or "")
                    if (
                        end is None
                        or filed is None
                        or end < cutoff
                        or form not in ANNUAL_FORMS | QUARTERLY_FORMS
                        or not accession
                        or not isinstance(raw.get("val"), int | float)
                    ):
                        continue
                    period_type = _period_type(spec, form, start, end)
                    if period_type is None:
                        continue
                    record = SecFinancialFactRecord(
                        code=code,
                        metric=spec.metric,
                        value=float(raw["val"]),
                        unit=unit.replace(" ", ""),
                        period_start=start,
                        period_end=end,
                        period_type=period_type,
                        fiscal_year=int(raw["fy"]) if isinstance(raw.get("fy"), int) else None,
                        fiscal_period=str(raw.get("fp") or "") or None,
                        form=form,
                        filed_at=filed,
                        accession_number=accession,
                        taxonomy=concept.taxonomy,
                        source_concept=concept.concept,
                        frame=str(raw.get("frame") or "") or None,
                        source_url=filing_index_url(cik, accession),
                    )
                    observations.append(record)
    return sorted(
        observations,
        key=lambda row: (
            row.metric,
            row.period_end,
            row.period_type,
            row.filed_at,
            row.accession_number,
            row.taxonomy,
            row.source_concept,
        ),
    )


def select_company_fact_projection(
    observations: list[SecFinancialFactRecord],
) -> list[SecFinancialFactRecord]:
    """Select the latest preferred concept per period for the operational projection."""
    concept_priority = {
        (spec.metric, concept.taxonomy, concept.concept): priority
        for spec in METRIC_SPECS
        for priority, concept in enumerate(spec.concepts)
    }
    selected: dict[tuple[str, dt.date, str], tuple[int, SecFinancialFactRecord]] = {}
    for record in observations:
        priority = concept_priority.get(
            (record.metric, record.taxonomy, record.source_concept),
            len(METRIC_SPECS),
        )
        key = (record.metric, record.period_end, record.period_type)
        prior = selected.get(key)
        rank = (record.filed_at.toordinal(), -priority)
        prior_rank = (prior[1].filed_at.toordinal(), -prior[0]) if prior is not None else None
        if prior_rank is None or rank > prior_rank:
            selected[key] = (priority, record)

    by_metric: dict[str, list[SecFinancialFactRecord]] = {}
    for _, record in selected.values():
        by_metric.setdefault(record.metric, []).append(record)
    out: list[SecFinancialFactRecord] = []
    for metric, rows in by_metric.items():
        rows = _normalized_periods(rows, metric)
        rows.sort(key=lambda row: (row.period_end, row.filed_at), reverse=True)
        out.extend(rows[:MAX_FACT_PERIODS])
    return sorted(out, key=lambda row: (row.metric, row.period_end, row.period_type))


def parse_company_facts(
    code: str,
    cik: int,
    payload: Mapping[str, Any],
    *,
    today: dt.date | None = None,
) -> list[SecFinancialFactRecord]:
    """Return the bounded latest-fact projection used by portal fundamentals."""
    return select_company_fact_projection(
        parse_company_fact_observations(code, cik, payload, today=today)
    )


class SecEdgarClient:
    """Small respectful client; one process stays well below the SEC's 10 req/s ceiling."""

    def __init__(
        self,
        user_agent: str,
        *,
        requests_per_second: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not user_agent.strip() or "@" not in user_agent:
            raise ValueError(
                "SEC User-Agent must identify the product and a monitored contact email"
            )
        self._headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json",
        }
        self._interval = 1 / requests_per_second
        self._last_request = 0.0
        self._transport = transport

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        path: str,
        *,
        allow_not_found: bool = False,
    ) -> dict[str, Any]:
        for attempt in range(4):
            delay = self._interval - (time.monotonic() - self._last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request = time.monotonic()
            response = await client.get(path)
            if allow_not_found and response.status_code == 404:
                return {}
            if response.status_code not in {429, 500, 502, 503, 504}:
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError(f"SEC endpoint {path} returned a non-object payload")
                return data
            await asyncio.sleep(2**attempt)
        response.raise_for_status()
        raise AssertionError("unreachable")

    async def fetch_company(self, cik: int) -> tuple[dict[str, Any], dict[str, Any]]:
        padded = f"{cik:010d}"
        async with httpx.AsyncClient(
            base_url=DATA_BASE,
            headers=self._headers,
            timeout=45,
            follow_redirects=True,
            transport=self._transport,
        ) as client:
            submissions = await self._get_json(client, f"/submissions/CIK{padded}.json")
            company_facts = await self._get_json(
                client,
                f"/api/xbrl/companyfacts/CIK{padded}.json",
                allow_not_found=True,
            )
        return submissions, company_facts
