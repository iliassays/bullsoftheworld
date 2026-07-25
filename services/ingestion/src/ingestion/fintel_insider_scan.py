"""Fintel-style insider algo scan — read-only leaderboard over ``insider_transactions``.

Ranks US issuers by the opportunistic insider cluster-buy evidence in
``bulls.analytics.fintel_insider_algo``. Read-only by design: it writes no table, feeds no paper
book, and creates no strategy. Under the Atlas mandate this is a descriptive evidence surface
that has not been through a promotion gate, so its output is "here is what insiders filed",
never "here is what to own".

``known_at`` is the EDGAR acceptance timestamp, falling back to when we captured the filing.
Selecting on it (rather than on the transaction date) is what keeps a historical run honest: a
Form 4 is due two business days after the trade, so the transaction date is not a moment anyone
could have acted on.

EDGAR is US-only, so this scan is implicitly market ``US``.

One-shot:
    uv run python -m ingestion.fintel_insider_scan
    uv run python -m ingestion.fintel_insider_scan --as-of 2026-06-30 --min-buyers 2 --json
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import logging
import sys
from collections import defaultdict
from dataclasses import asdict

from sqlalchemy import func, or_, select

from bulls.analytics.fintel_insider_algo import (
    ACQUIRED,
    DEFAULT_WINDOW_DAYS,
    METHODOLOGY_VERSION,
    OPEN_MARKET_PURCHASE_CODE,
    InsiderTrade,
    evaluate_fintel_insider_algo,
)
from bulls.core.db import get_sessionmaker
from bulls.core.models import EdgarFilingEvent, InsiderTransaction

log = logging.getLogger(__name__)

# Years of history loaded behind the window so the calendar-routine classifier can see a
# multi-year pattern. Three years is the minimum it needs; five gives it room to be sure.
DEFAULT_HISTORY_YEARS = 5


def _known_at_column():
    """EDGAR acceptance if we have it, else our capture time. Never the transaction date."""
    return func.coalesce(
        EdgarFilingEvent.accepted_at,
        EdgarFilingEvent.captured_at,
        InsiderTransaction.captured_at,
    )


async def _issuers_with_recent_purchases(session, *, as_of: dt.date, window_days: int) -> list[int]:
    """Issuers with at least one non-plan open-market purchase public inside the window."""
    known_at = _known_at_column()
    cutoff = dt.datetime.combine(as_of, dt.time.max, tzinfo=dt.UTC)
    floor = dt.datetime.combine(as_of - dt.timedelta(days=window_days), dt.time.min, tzinfo=dt.UTC)
    stmt = (
        select(InsiderTransaction.issuer_cik)
        .join(
            EdgarFilingEvent,
            EdgarFilingEvent.accession_number == InsiderTransaction.accession_number,
            isouter=True,
        )
        .where(
            InsiderTransaction.code == OPEN_MARKET_PURCHASE_CODE,
            InsiderTransaction.acquired_disposed == ACQUIRED,
            InsiderTransaction.shares > 0,
            InsiderTransaction.is_10b5_1_plan.is_(False),
            or_(
                InsiderTransaction.is_officer.is_(True),
                InsiderTransaction.is_director.is_(True),
            ),
            known_at <= cutoff,
            known_at >= floor,
        )
        .group_by(InsiderTransaction.issuer_cik)
    )
    return [row[0] for row in await session.execute(stmt)]


async def _load_history(
    session, issuer_ciks: list[int], *, as_of: dt.date, history_years: int
) -> dict[int, tuple[str | None, list[InsiderTrade]]]:
    """Full purchase history per issuer: (best-known symbol, trades)."""
    if not issuer_ciks:
        return {}
    known_at = _known_at_column()
    cutoff = dt.datetime.combine(as_of, dt.time.max, tzinfo=dt.UTC)
    floor = dt.date(as_of.year - history_years, as_of.month, as_of.day)
    stmt = (
        select(
            InsiderTransaction.issuer_cik,
            InsiderTransaction.issuer_symbol,
            InsiderTransaction.owner_cik,
            InsiderTransaction.owner_name,
            InsiderTransaction.officer_title,
            InsiderTransaction.transaction_date,
            InsiderTransaction.code,
            InsiderTransaction.acquired_disposed,
            InsiderTransaction.shares,
            InsiderTransaction.price_per_share,
            InsiderTransaction.shares_owned_after,
            InsiderTransaction.is_officer,
            InsiderTransaction.is_director,
            InsiderTransaction.is_ten_percent_owner,
            InsiderTransaction.is_10b5_1_plan,
            known_at.label("known_at"),
        )
        .join(
            EdgarFilingEvent,
            EdgarFilingEvent.accession_number == InsiderTransaction.accession_number,
            isouter=True,
        )
        .where(
            InsiderTransaction.issuer_cik.in_(issuer_ciks),
            InsiderTransaction.code == OPEN_MARKET_PURCHASE_CODE,
            known_at <= cutoff,
            # Undated rows (the repaired typos) are kept: the algo counts them as abstentions
            # rather than pretending they fall outside the window.
            or_(
                InsiderTransaction.transaction_date.is_(None),
                InsiderTransaction.transaction_date >= floor,
            ),
        )
    )

    trades: dict[int, list[InsiderTrade]] = defaultdict(list)
    symbols: dict[int, str] = {}
    for row in await session.execute(stmt):
        if row.issuer_symbol and row.issuer_cik not in symbols:
            symbols[row.issuer_cik] = row.issuer_symbol
        trades[row.issuer_cik].append(
            InsiderTrade(
                owner_cik=row.owner_cik,
                known_at=row.known_at,
                transaction_date=row.transaction_date,
                owner_name=row.owner_name,
                officer_title=row.officer_title,
                code=row.code,
                acquired_disposed=row.acquired_disposed,
                shares=row.shares,
                price_per_share=row.price_per_share,
                shares_owned_after=row.shares_owned_after,
                is_officer=row.is_officer,
                is_director=row.is_director,
                is_ten_percent_owner=row.is_ten_percent_owner,
                is_10b5_1_plan=row.is_10b5_1_plan,
            )
        )
    return {cik: (symbols.get(cik), rows) for cik, rows in trades.items()}


async def run_fintel_insider_scan(
    *,
    as_of: dt.date,
    window_days: int = DEFAULT_WINDOW_DAYS,
    history_years: int = DEFAULT_HISTORY_YEARS,
    min_buyers: int = 1,
    limit: int = 25,
) -> list[dict]:
    """Evaluate every issuer with a recent purchase; return the ranked leaderboard."""
    sm = get_sessionmaker()
    async with sm() as session:
        issuers = await _issuers_with_recent_purchases(
            session, as_of=as_of, window_days=window_days
        )
        history = await _load_history(session, issuers, as_of=as_of, history_years=history_years)

    rows: list[dict] = []
    for issuer_cik, (symbol, trades) in history.items():
        read = evaluate_fintel_insider_algo(trades, as_of=as_of, window_days=window_days)
        if read is None or read.qualifying_buyers < max(1, min_buyers):
            continue
        rows.append({"issuer_cik": issuer_cik, "symbol": symbol, **asdict(read)})

    rows.sort(
        key=lambda row: (row["score"], row["qualifying_buyers"], row["purchases"]),
        reverse=True,
    )
    log.info(
        "fintel_insider_scan as_of=%s evaluated=%s qualified=%s version=%s",
        as_of,
        len(history),
        len(rows),
        METHODOLOGY_VERSION,
    )
    return rows[:limit]


def _format(rows: list[dict], *, as_of: dt.date, window_days: int) -> str:
    if not rows:
        return f"[fintel-insider] no qualifying cluster in the {window_days} days to {as_of}."
    lines = [
        f"[fintel-insider] {METHODOLOGY_VERSION} — {window_days}d to {as_of} "
        f"({len(rows)} issuers). Descriptive evidence, not a validated signal.",
        f"{'SYMBOL':<10}{'SCORE':>6}{'BAND':>16}{'BUYERS':>8}{'BUYS':>6}  {'VALUE':>14}",
    ]
    for row in rows:
        value = row["aggregate_value_usd"]
        value_text = (
            "—" if value is None else f"${value:,.0f}{'+' if row['value_is_partial'] else ''}"
        )
        lines.append(
            f"{row['symbol'] or row['issuer_cik']:<10}"
            f"{row['score']:>6}{row['band']:>16}"
            f"{row['qualifying_buyers']:>8}{row['purchases']:>6}  {value_text:>14}"
        )
    return "\n".join(lines)


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fintel-style insider cluster-buy leaderboard")
    parser.add_argument("--as-of", type=dt.date.fromisoformat, default=None)
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument("--history-years", type=int, default=DEFAULT_HISTORY_YEARS)
    parser.add_argument("--min-buyers", type=int, default=1)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--json", action="store_true", help="emit the full reads as JSON")
    return parser.parse_args(argv)


def main() -> None:
    args = _args()
    as_of = args.as_of or dt.datetime.now(dt.UTC).date()
    rows = asyncio.run(
        run_fintel_insider_scan(
            as_of=as_of,
            window_days=args.window_days,
            history_years=args.history_years,
            min_buyers=args.min_buyers,
            limit=args.limit,
        )
    )
    if args.json:
        json.dump(rows, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return
    print(_format(rows, as_of=as_of, window_days=args.window_days))
    for row in rows[:5]:
        print(f"\n  {row['symbol'] or row['issuer_cik']}:")
        for line in row["evidence"]:
            print(f"    - {line}")


if __name__ == "__main__":
    main()
