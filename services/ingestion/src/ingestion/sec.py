"""Incremental SEC submissions and selected Company Facts ingestion for retail-ready US symbols.

The SEC JSON payloads are parsed in memory and discarded. PostgreSQL receives only compact filing
metadata and a bounded whitelist of normalized financial facts.

    uv run python -m ingestion.sec --market US
    uv run python -m ingestion.sec --market US --codes AAPL,MSFT
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import itertools
from collections import defaultdict

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.config import get_settings
from bulls.core.db import get_sessionmaker
from bulls.core.models import (
    AnnualFinancial,
    CompanyProfile,
    DividendRecord,
    RegulatoryDataState,
    SecFiling,
    SecFinancialFact,
    SecurityMaster,
    Symbol,
)
from bulls.market_data.providers.sec_edgar import (
    FILING_RETENTION_YEARS,
    SecEdgarClient,
    SecFinancialFactRecord,
    SecIssuerProfile,
    parse_company_facts,
    parse_submissions,
    years_ago,
)

MARKET = "US"
SOURCE = "sec_edgar"


def _sector_from_sic(sic: str | None, fallback: str | None) -> str | None:
    fallback = fallback[:64] if fallback else None
    try:
        code = int(sic or "")
    except ValueError:
        return fallback
    if 2830 <= code <= 2836 or 3840 <= code <= 3851 or 8000 <= code <= 8099:
        return "Health Care"
    if 3570 <= code <= 3579 or 3660 <= code <= 3699 or 7370 <= code <= 7379:
        return "Technology"
    if 4810 <= code <= 4899:
        return "Communication Services"
    if 4900 <= code <= 4999:
        return "Utilities"
    if 6000 <= code <= 6499:
        return "Financials"
    if 6500 <= code <= 6799:
        return "Real Estate"
    if 1000 <= code <= 1499 or code == 2911:
        return "Energy & Mining"
    if 2000 <= code <= 2199:
        return "Consumer Staples"
    if 2200 <= code <= 2399 or 3700 <= code <= 3799 or 5000 <= code <= 5999:
        return "Consumer Discretionary"
    if 2800 <= code <= 2899:
        return "Materials"
    if 1500 <= code <= 1999 or 2400 <= code <= 3999 or 4000 <= code <= 4799:
        return "Industrials"
    if 7000 <= code <= 8999:
        return "Business & Consumer Services"
    return fallback


def _user_agent() -> str:
    settings = get_settings()
    contact = settings.sec_contact_email
    return f"BullsOfTheWorld/1.0 {contact}"


def _metric_rows(
    rows: list[SecFinancialFactRecord], metric: str, period_type: str | None = None
) -> list[SecFinancialFactRecord]:
    selected = [
        row
        for row in rows
        if row.metric == metric and (period_type is None or row.period_type == period_type)
    ]
    return sorted(selected, key=lambda row: (row.period_end, row.filed_at), reverse=True)


def _latest_value(
    rows: list[SecFinancialFactRecord], metric: str, period_type: str | None = None
) -> float | None:
    candidates = _metric_rows(rows, metric, period_type)
    return candidates[0].value if candidates else None


def _ttm_value(rows: list[SecFinancialFactRecord], metric: str) -> float | None:
    quarterly = _metric_rows(rows, metric, "quarter")
    latest_four = quarterly[:4]
    if len(latest_four) == 4 and all(
        60 <= (newer.period_end - older.period_end).days <= 130
        for newer, older in itertools.pairwise(latest_four)
    ):
        return sum(row.value for row in latest_four)
    annual = _metric_rows(rows, metric, "annual")
    if not annual:
        return None
    latest_annual = annual[0]
    newer = [row for row in quarterly if row.period_end > latest_annual.period_end]
    if not newer:
        return latest_annual.value
    replacements: list[tuple[SecFinancialFactRecord, SecFinancialFactRecord]] = []
    for current in newer:
        prior = next(
            (
                candidate
                for candidate in quarterly
                if 345 <= (current.period_end - candidate.period_end).days <= 385
            ),
            None,
        )
        if prior is None:
            return latest_annual.value
        replacements.append((current, prior))
    return latest_annual.value + sum(cur.value - prev.value for cur, prev in replacements)


def _profile_row(
    code: str,
    issuer: SecIssuerProfile,
    facts: list[SecFinancialFactRecord],
    fetched_at: dt.datetime,
    instrument_type: str,
    per_share_compatible: bool,
) -> dict:
    sector = _sector_from_sic(issuer.sic, issuer.sic_description)
    shares = _latest_value(facts, "shares_outstanding", "instant") if per_share_compatible else None
    equity = _latest_value(facts, "equity", "instant")
    eps = _ttm_value(facts, "eps_diluted") if per_share_compatible else None
    if eps is None and per_share_compatible:
        eps = _ttm_value(facts, "eps_basic")
    if eps is None and per_share_compatible:
        income = _ttm_value(facts, "net_income")
        eps = income / shares if income is not None and shares else None
    nav = equity / shares if equity is not None and shares and shares > 0 else None
    debt_current = _latest_value(facts, "debt_current", "instant")
    debt_noncurrent = _latest_value(facts, "debt_noncurrent", "instant")
    debt_total = _latest_value(facts, "debt_total", "instant")
    if debt_noncurrent is None and debt_total is not None:
        debt_noncurrent = max(0.0, debt_total - (debt_current or 0.0))
    return {
        "market": MARKET,
        "code": code,
        "sector": sector,
        "instrument_type": instrument_type,
        "outstanding_shares": round(shares) if shares and shares > 0 else None,
        "eps": eps,
        "nav_per_share": nav,
        "short_term_loan_mn": debt_current / 1e6 if debt_current is not None else None,
        "long_term_loan_mn": debt_noncurrent / 1e6 if debt_noncurrent is not None else None,
        "reserve_surplus_mn": equity / 1e6 if equity is not None else None,
        "year_end": issuer.fiscal_year_end,
        "operational_status": "active",
        "fetched_at": fetched_at,
    }


def _annual_rows(
    code: str, facts: list[SecFinancialFactRecord], *, per_share_compatible: bool
) -> list[dict]:
    by_year: dict[int, dict[str, SecFinancialFactRecord]] = defaultdict(dict)
    for metric in ("eps_diluted", "eps_basic", "net_income"):
        for row in _metric_rows(facts, metric, "annual"):
            year = row.fiscal_year or row.period_end.year
            by_year[year].setdefault(metric, row)
    out: list[dict] = []
    for year, metrics in sorted(by_year.items(), reverse=True)[:8]:
        eps = (
            (metrics.get("eps_diluted") or metrics.get("eps_basic"))
            if per_share_compatible
            else None
        )
        profit = metrics.get("net_income")
        out.append(
            {
                "market": MARKET,
                "code": code,
                "fiscal_year": year,
                "eps": eps.value if eps else None,
                "nav_per_share": None,
                "profit_mn": profit.value / 1e6 if profit else None,
            }
        )
    return out


def _dividend_rows(code: str, facts: list[SecFinancialFactRecord]) -> list[dict]:
    out: list[dict] = []
    seen: set[int] = set()
    for row in _metric_rows(facts, "dividends_per_share", "annual"):
        year = row.fiscal_year or row.period_end.year
        if year in seen:
            continue
        seen.add(year)
        out.append(
            {
                "market": MARKET,
                "code": code,
                "year": year,
                "cash_pct": None,
                "cash_per_share": row.value,
                "bonus_pct": None,
            }
        )
    return out[:8]


async def _upsert(session, model, rows: list[dict], keys: tuple[str, ...]) -> int:
    if not rows:
        return 0
    stmt = pg_insert(model).values(rows)
    updates = {column: getattr(stmt.excluded, column) for column in rows[0] if column not in keys}
    await session.execute(stmt.on_conflict_do_update(index_elements=list(keys), set_=updates))
    return len(rows)


async def _persist_company(
    code: str,
    issuer: SecIssuerProfile,
    filings,
    facts: list[SecFinancialFactRecord],
    fetched_at: dt.datetime,
    instrument_type: str,
    per_share_compatible: bool,
) -> tuple[int, int]:
    sm = get_sessionmaker()
    async with sm() as session:
        filing_rows = [row.model_dump() for row in filings]
        fact_rows = [row.model_dump() for row in facts]
        filing_count = await _upsert(
            session, SecFiling, filing_rows, ("market", "code", "accession_number")
        )

        # Company Facts is a complete bounded projection for this code. Replacing it prevents stale
        # concepts or superseded amendments from accumulating indefinitely.
        await session.execute(
            delete(SecFinancialFact).where(
                SecFinancialFact.market == MARKET, SecFinancialFact.code == code
            )
        )
        fact_count = await _upsert(
            session,
            SecFinancialFact,
            fact_rows,
            ("market", "code", "metric", "period_end", "period_type"),
        )
        await _upsert(
            session,
            CompanyProfile,
            [
                _profile_row(
                    code,
                    issuer,
                    facts,
                    fetched_at,
                    instrument_type,
                    per_share_compatible,
                )
            ],
            ("market", "code"),
        )
        await session.execute(
            delete(AnnualFinancial).where(
                AnnualFinancial.market == MARKET, AnnualFinancial.code == code
            )
        )
        await session.execute(
            delete(DividendRecord).where(
                DividendRecord.market == MARKET, DividendRecord.code == code
            )
        )
        await _upsert(
            session,
            AnnualFinancial,
            _annual_rows(
                code,
                facts,
                per_share_compatible=per_share_compatible,
            ),
            ("market", "code", "fiscal_year"),
        )
        await _upsert(
            session,
            DividendRecord,
            _dividend_rows(code, facts) if per_share_compatible else [],
            ("market", "code", "year"),
        )
        sector = _sector_from_sic(issuer.sic, issuer.sic_description)
        if sector:
            await session.execute(
                update(Symbol)
                .where(Symbol.market == MARKET, Symbol.code == code)
                .values(sector=sector)
            )
        cutoff = years_ago(fetched_at.date(), FILING_RETENTION_YEARS)
        await session.execute(
            delete(SecFiling).where(
                SecFiling.market == MARKET,
                SecFiling.code == code,
                SecFiling.filing_date < cutoff,
            )
        )
        await session.commit()
    return filing_count, fact_count


async def _ready_cik_codes(codes: list[str] | None = None) -> list[tuple[str, int, str, bool]]:
    sm = get_sessionmaker()
    async with sm() as session:
        stmt = (
            select(Symbol.code, SecurityMaster.cik, SecurityMaster.instrument_type)
            .join(
                SecurityMaster,
                (SecurityMaster.market == Symbol.market) & (SecurityMaster.symbol == Symbol.code),
            )
            .where(
                Symbol.market == MARKET,
                Symbol.is_active.is_(True),
                Symbol.is_hidden.is_(False),
                Symbol.data_status == "ready",
                SecurityMaster.cik.isnot(None),
            )
            .order_by(Symbol.code)
        )
        if codes:
            stmt = stmt.where(Symbol.code.in_(codes))
        rows = (await session.execute(stmt)).all()
        cik_counts = dict(
            (
                await session.execute(
                    select(SecurityMaster.cik, func.count())
                    .where(
                        SecurityMaster.market == MARKET,
                        SecurityMaster.is_active.is_(True),
                        SecurityMaster.is_product_eligible.is_(True),
                        SecurityMaster.cik.isnot(None),
                    )
                    .group_by(SecurityMaster.cik)
                )
            ).all()
        )
        return [
            (
                code,
                int(cik),
                instrument_type,
                instrument_type == "common_stock" and cik_counts.get(cik, 0) == 1,
            )
            for code, cik, instrument_type in rows
        ]


async def collect(*, codes: list[str] | None = None) -> dict[str, int]:
    selected = await _ready_cik_codes(codes)
    client = SecEdgarClient(_user_agent())
    fetched_at = dt.datetime.now(dt.UTC)
    filings_total = 0
    facts_total = 0
    completed = 0
    failed = 0
    indexed_codes: list[str] = []
    filing_sources: set[tuple[str, str]] = set()
    for index, (code, cik, instrument_type, per_share_compatible) in enumerate(selected, start=1):
        try:
            submissions, company_facts = await client.fetch_company(cik)
            issuer, filings = parse_submissions(code, submissions, fetched_at=fetched_at)
            facts = parse_company_facts(code, cik, company_facts, today=fetched_at.date())
            filing_count, fact_count = await _persist_company(
                code,
                issuer,
                filings,
                facts,
                fetched_at,
                instrument_type,
                per_share_compatible,
            )
            filings_total += filing_count
            facts_total += fact_count
            completed += 1
            indexed_codes.append(code)
            filing_sources.update((code, row.accession_number) for row in filings)
        except Exception as error:
            failed += 1
            print(f"  ! {code}: SEC refresh failed ({error})")
        if index % 10 == 0 or index == len(selected):
            print(f"  ...{index}/{len(selected)} symbols")

    if selected and completed == 0:
        raise RuntimeError(f"SEC refresh failed for all {len(selected)} selected symbols")

    sm = get_sessionmaker()
    async with sm() as session:
        state = {
            "market": MARKET,
            "source": SOURCE,
            "as_of_date": fetched_at.date(),
            "last_success_at": fetched_at,
            "records": filings_total + facts_total,
            "symbols_covered": completed,
            "downloaded_bytes": 0,
            "details": {
                "symbols_requested": len(selected),
                "symbols_failed": failed,
                "filings": filings_total,
                "facts": facts_total,
                "retention": "selected facts 8y/24 periods; filing metadata 7y; no raw JSON",
            },
        }
        await _upsert(session, RegulatoryDataState, [state], ("market", "source"))
        await session.commit()
    if completed:
        settings = get_settings()
        redis = await create_pool(
            RedisSettings.from_dsn(settings.redis_url),
            default_queue_name=settings.ai_queue_name,
        )
        try:
            for code, accession in filing_sources:
                await redis.enqueue_job(
                    "embed_sec_filing",
                    MARKET,
                    code,
                    accession,
                    _job_id=f"embed:sec:{MARKET}:{code}:{accession}",
                )
            for code in indexed_codes:
                await redis.enqueue_job(
                    "embed_sec_financials",
                    MARKET,
                    code,
                    _job_id=f"embed:sec-facts:{MARKET}:{code}:{fetched_at.date()}",
                )
        finally:
            await redis.aclose()
    return {
        "symbols": len(selected),
        "completed": completed,
        "failed": failed,
        "filings": filings_total,
        "facts": facts_total,
    }


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest normalized SEC evidence")
    parser.add_argument("--market", default=MARKET, choices=[MARKET])
    parser.add_argument("--codes", help="comma-separated ready symbol codes")
    return parser.parse_args()


def main() -> None:
    args = _args()
    codes = [code.strip().upper() for code in args.codes.split(",")] if args.codes else None
    print(f"[sec] refreshing {args.market} filings and Company Facts")
    stats = asyncio.run(collect(codes=codes))
    print(f"[sec] done: {stats}")


if __name__ == "__main__":
    main()
