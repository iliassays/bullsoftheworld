"""Run System A (the filings-event follower) end to end against real recorded data.

The chain the institutional study specifies for its #5-ranked, best-free-signal candidate:

  insider Form 4 stream  -> classify routine/opportunistic (Cohen-Malloy-Pomorski) -> P-code,
    non-plan, opportunistic purchases -> cluster by issuer on dissemination time
  activist 13D stream    -> keep new filings by a curated multi-campaign roster
    -> combine into dated candidate events
      -> screen (measured spread gate + point-in-time market-cap floor) with rejections logged
        -> walk the book forward (exit-then-enter, 1/N, position + concurrency caps, time stop)
          -> the shared execution engine at measured per-name cost -> deflated Sharpe

Point-in-time throughout: every event is stamped with its EDGAR *acceptance* time, never the
transaction date, and market-cap uses only fundamentals filed by the signal date. Read-only:
nothing is placed, nothing persisted.

**Two-phase and memory-lean by design.** The insider table holds ~1.7M rows and the market has
~11k symbols; materialising all of that as objects OOMs the box. So classification runs off a
light (owner, date) projection, only P-code purchases in the window are hydrated, and prices are
loaded for exactly the few hundred names that actually become candidates -- never the whole market.

Honest limitation carried into the output: the crowding screen is disabled because we ingest
short *volume*, not short interest as a percent of float. The book runs two of its three entry
gates. This is a recorded gap, not a silent one.

Usage::

    python -m ingestion.system_a_backtest --start 2021-07-01
"""

from __future__ import annotations

import argparse
import asyncio
import bisect
import datetime as dt
import json
import sys
from collections import defaultdict
from typing import Any

from sqlalchemy import distinct, select

from bulls.analytics.cost_observatory import estimate_spread
from bulls.analytics.deflated_sharpe import deflated_sharpe_ratio
from bulls.analytics.factor_sleeve import (
    FundamentalObservation,
    point_in_time_factor_fundamentals,
)
from bulls.analytics.filing_book import (
    BookPolicy,
    CandidateEvent,
    CandidateMarketState,
    build_weight_schedule,
    rejection_summary,
    screen_candidates,
)
from bulls.analytics.filing_signals import (
    ActivistEvent,
    ActivistRoster,
    InsiderTrade,
    classify_insider,
    detect_clusters,
    qualifying_activist_events,
    qualifying_purchases,
)
from bulls.analytics.research_strategy import (
    BenchmarkPoint,
    BenchmarkSeries,
    StrategyBar,
    StrategySecurity,
    run_cost_tiered_backtest,
)
from bulls.core.db import get_sessionmaker
from bulls.core.models import (
    DailyBar,
    EdgarFilingEvent,
    InsiderTransaction,
    OwnershipStakeEvent,
    SecFinancialFactObservation,
    SecurityMaster,
)
from bulls.market_data.providers.sec_edgar import METRIC_SPECS

# Documented multi-campaign activists (Phase 1/9 tier). Filer selection IS the strategy: the
# aggregate 13D universe carries no reliable edge, so this is an allow-list, not a screen.
_ACTIVIST_FRAGMENTS = (
    "elliott",
    "third point",
    "pershing square",
    "valueact",
    "starboard value",
    "icahn",
    "trian",
    "jana partners",
    "corvex",
    "sachem head",
    "engaged capital",
    "legion partners",
    "ancora",
    "politan",
    "engine capital",
    "carl c",
    "value act",
    "scion",
    "cannell",
    "barington",
    "land & buildings",
    "impactive",
    "inclusive capital",
    "sarissa",
)
_CONCEPT_PRIORITY = {
    (spec.metric, concept.taxonomy, concept.concept): priority
    for spec in METRIC_SPECS
    for priority, concept in enumerate(spec.concepts)
}


async def _load_events(start: dt.date):
    """Phase 1: everything needed to decide candidates, without touching prices."""
    sm = get_sessionmaker()
    async with sm() as s:
        candidate_owners = (
            select(distinct(InsiderTransaction.owner_cik))
            .join(
                EdgarFilingEvent,
                EdgarFilingEvent.accession_number == InsiderTransaction.accession_number,
            )
            .where(
                InsiderTransaction.code == "P",
                EdgarFilingEvent.accepted_at.is_not(None),
                EdgarFilingEvent.accepted_at >= start - dt.timedelta(days=45),
            )
        )
        # Light point-in-time projection for only owners who can enter the test window. Acceptance
        # time is mandatory: final-history classification would leak later behavior backwards.
        class_rows = list(
            await s.execute(
                select(
                    InsiderTransaction.owner_cik,
                    InsiderTransaction.transaction_date,
                    EdgarFilingEvent.accepted_at,
                )
                .join(
                    EdgarFilingEvent,
                    EdgarFilingEvent.accession_number == InsiderTransaction.accession_number,
                )
                .where(
                    InsiderTransaction.owner_cik.in_(candidate_owners),
                    InsiderTransaction.transaction_date.is_not(None),
                    # Guard against residual impossible Form 4 dates that predate the
                    # ingestion-time rejection (commit 82cdd8e); 32 such rows remain in prod.
                    InsiderTransaction.transaction_date >= dt.date(1990, 1, 1),
                    InsiderTransaction.transaction_date <= dt.date(2030, 12, 31),
                    EdgarFilingEvent.accepted_at.is_not(None),
                )
                .order_by(InsiderTransaction.owner_cik, EdgarFilingEvent.accepted_at)
            )
        )
        # CIK -> symbol bridge. The security master is the authoritative source (it resolves
        # activist 13D targets that never appear in the insider stream); the insider table's own
        # paired columns are a fallback for anything the master is missing.
        master_rows = list(
            await s.execute(
                select(SecurityMaster.cik, SecurityMaster.symbol).where(
                    SecurityMaster.market == "US", SecurityMaster.cik.is_not(None)
                )
            )
        )
        bridge_rows = list(
            await s.execute(
                select(
                    distinct(InsiderTransaction.issuer_cik), InsiderTransaction.issuer_symbol
                ).where(InsiderTransaction.issuer_symbol.is_not(None))
            )
        )
        # Only open-market purchases disseminated in the window can become candidates; hydrate
        # just those (a small fraction of the 1.7M rows).
        purchase_rows = list(
            await s.execute(
                select(
                    InsiderTransaction.issuer_cik,
                    InsiderTransaction.issuer_symbol,
                    InsiderTransaction.owner_cik,
                    InsiderTransaction.transaction_date,
                    InsiderTransaction.code,
                    InsiderTransaction.shares,
                    InsiderTransaction.price_per_share,
                    InsiderTransaction.is_10b5_1_plan,
                    InsiderTransaction.is_officer,
                    InsiderTransaction.is_director,
                    InsiderTransaction.is_ten_percent_owner,
                    EdgarFilingEvent.accepted_at,
                )
                .join(
                    EdgarFilingEvent,
                    EdgarFilingEvent.accession_number == InsiderTransaction.accession_number,
                )
                .where(
                    InsiderTransaction.code == "P",
                    InsiderTransaction.transaction_date.is_not(None),
                    # Guard against residual impossible Form 4 dates that predate the
                    # ingestion-time rejection (commit 82cdd8e); 32 such rows remain in prod.
                    InsiderTransaction.transaction_date >= dt.date(1990, 1, 1),
                    InsiderTransaction.transaction_date <= dt.date(2030, 12, 31),
                    EdgarFilingEvent.accepted_at.is_not(None),
                    EdgarFilingEvent.accepted_at >= start - dt.timedelta(days=45),
                )
            )
        )
        stake_rows = list(
            await s.execute(
                select(
                    OwnershipStakeEvent.accession_number,
                    OwnershipStakeEvent.subject_cik,
                    OwnershipStakeEvent.subject_name,
                    OwnershipStakeEvent.filed_by_cik,
                    OwnershipStakeEvent.filed_by_name,
                    OwnershipStakeEvent.form,
                    OwnershipStakeEvent.accepted_at,
                    OwnershipStakeEvent.percent_of_class,
                ).where(
                    OwnershipStakeEvent.form.like("%13%"),
                    OwnershipStakeEvent.accepted_at.is_not(None),
                )
            )
        )
    return class_rows, master_rows, bridge_rows, purchase_rows, stake_rows


async def _load_prices(codes: list[str], start: dt.date):
    """Phase 2: bars + shares only for the names that became candidates, chunked."""
    sm = get_sessionmaker()
    bar_rows: list = []
    fact_rows: list = []
    async with sm() as s:
        for i in range(0, len(codes), 400):
            chunk = codes[i : i + 400]
            bar_rows += list(
                await s.execute(
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
                        DailyBar.market == "US",
                        DailyBar.code.in_(chunk),
                        DailyBar.date >= start - dt.timedelta(days=400),
                    )
                    .order_by(DailyBar.code, DailyBar.date)
                )
            )
            fact_rows += list(
                await s.execute(
                    select(
                        SecFinancialFactObservation.code,
                        SecFinancialFactObservation.metric,
                        SecFinancialFactObservation.value,
                        SecFinancialFactObservation.unit,
                        SecFinancialFactObservation.period_start,
                        SecFinancialFactObservation.period_end,
                        SecFinancialFactObservation.period_type,
                        SecFinancialFactObservation.known_at,
                        SecFinancialFactObservation.accession_number,
                        SecFinancialFactObservation.taxonomy,
                        SecFinancialFactObservation.source_concept,
                    ).where(
                        SecFinancialFactObservation.market == "US",
                        SecFinancialFactObservation.code.in_(chunk),
                        SecFinancialFactObservation.metric == "shares_outstanding",
                    )
                )
            )
    return bar_rows, fact_rows


async def _load_benchmark(start: dt.date) -> BenchmarkSeries | None:
    sm = get_sessionmaker()
    async with sm() as session:
        rows = (
            await session.execute(
                select(DailyBar.date, DailyBar.close, DailyBar.adjusted_close)
                .where(
                    DailyBar.market == "US",
                    DailyBar.code == "SPY",
                    DailyBar.date >= start,
                )
                .order_by(DailyBar.date)
            )
        ).all()
    points = [
        BenchmarkPoint(
            date=row.date,
            close=float(row.adjusted_close if row.adjusted_close is not None else row.close),
        )
        for row in rows
        if (row.adjusted_close if row.adjusted_close is not None else row.close) > 0
    ]
    return (
        BenchmarkSeries(key="spy_total_return_proxy", label="SPY adjusted close", points=points)
        if points
        else None
    )


def _candidates(class_rows, master_rows, bridge_rows, purchase_rows, stake_rows, *, start, sleeve):
    # Each owner's history is ordered by when it became public. A candidate is classified from the
    # prefix visible at its own dissemination time, never from the final database.
    owner_history: dict[int, list[tuple[dt.datetime, dt.date]]] = defaultdict(list)
    for owner_cik, txn_date, accepted_at in class_rows:
        owner_history[owner_cik].append((accepted_at, txn_date))

    # Security master first (authoritative), then the insider pairs fill any gaps.
    cik_to_symbol = {cik: sym for cik, sym in bridge_rows if sym}
    cik_to_symbol.update({cik: sym for cik, sym in master_rows if sym})

    trades = [
        InsiderTrade(
            issuer_cik=r.issuer_cik,
            issuer_symbol=r.issuer_symbol,
            owner_cik=r.owner_cik,
            transaction_date=r.transaction_date,
            disseminated_at=r.accepted_at,
            code=r.code,
            shares=r.shares,
            price_per_share=r.price_per_share,
            is_10b5_1_plan=r.is_10b5_1_plan,
            is_officer=r.is_officer,
            is_director=r.is_director,
            is_ten_percent_owner=r.is_ten_percent_owner,
        )
        for r in purchase_rows
    ]
    purchases: list[InsiderTrade] = []
    for trade in sorted(trades, key=lambda item: item.disseminated_at):
        history = owner_history.get(trade.owner_cik, [])
        cut = bisect.bisect_right(
            [known_at for known_at, _ in history],
            trade.disseminated_at,
        )
        classification = classify_insider([date for _, date in history[:cut]])
        purchases.extend(qualifying_purchases([trade], {trade.owner_cik: classification}))
    purchases = [trade for trade in purchases if trade.issuer_symbol]
    clusters = detect_clusters(purchases, window_days=30, minimum_insiders=1)
    insider_candidates = [
        CandidateEvent(
            symbol=c.issuer_symbol,
            issuer_cik=c.issuer_cik,
            kind="insider_cluster",
            signal_at=c.signal_at,
            strength=c.distinct_insiders + (0.5 if c.includes_officer_or_director else 0.0),
        )
        for c in clusters
        if c.issuer_symbol and c.signal_at.date() >= start
    ]

    roster = ActivistRoster(name_fragments=_ACTIVIST_FRAGMENTS)
    activist_events = [
        ActivistEvent(
            accession_number=r.accession_number,
            subject_cik=r.subject_cik,
            subject_name=r.subject_name,
            filed_by_cik=r.filed_by_cik,
            filed_by_name=r.filed_by_name,
            form=r.form,
            signal_at=r.accepted_at,
            percent_of_class=r.percent_of_class,
            is_amendment="/A" in (r.form or ""),
        )
        for r in stake_rows
        if "13D" in (r.form or "").upper()
    ]
    activist_candidates = [
        CandidateEvent(
            symbol=cik_to_symbol[e.subject_cik],
            issuer_cik=e.subject_cik,
            kind="activist_13d",
            signal_at=e.signal_at,
            strength=5.0,
        )
        for e in qualifying_activist_events(activist_events, roster)
        if e.subject_cik in cik_to_symbol and e.signal_at.date() >= start
    ]

    # Sleeve isolation: the two signals differ in kind and volume (thousands of insider clusters
    # vs dozens of activist 13Ds), so testing each alone answers a distinct pre-registered claim.
    candidates = insider_candidates if sleeve == "insider" else activist_candidates
    diag = {
        "sleeve": sleeve,
        "classified_insiders": len(owner_history),
        "opportunistic_purchases": len(purchases),
        "insider_clusters": len(insider_candidates),
        "activist_events": len(activist_candidates),
        "cik_symbol_bridge": len(cik_to_symbol),
    }
    return candidates, diag


def _market_state_on(symbol, as_of, spreads, bars, pit_shares) -> CandidateMarketState:
    close = None
    for b in bars.get(symbol, []):
        if b.date <= as_of:
            close = b.close
        else:
            break
    shares = pit_shares.get(symbol, {}).get("shares_outstanding")
    return CandidateMarketState(
        half_spread_bps=spreads.get(symbol),
        short_interest_pct_of_float=None,
        market_cap_mn=(close * shares / 1_000_000) if close and shares else None,
    )


def _spread_as_of(
    symbol: str,
    as_of: dt.date,
    bars: dict[str, list[StrategyBar]],
) -> float | None:
    completed = [bar for bar in bars.get(symbol, []) if bar.date <= as_of][-60:]
    estimate = estimate_spread(
        symbol,
        [bar.high for bar in completed],
        [bar.low for bar in completed],
    )
    return estimate.half_spread_bps if estimate is not None else None


def _session_for_signal(
    signal_at: dt.datetime,
    session_dates: list[dt.date],
) -> dt.datetime | None:
    index = bisect.bisect_left(session_dates, signal_at.date())
    if index >= len(session_dates):
        return None
    return dt.datetime.combine(session_dates[index], dt.time.max, tzinfo=dt.UTC)


def _thesis_breaks(
    stake_rows,
    *,
    master_rows,
    bridge_rows,
    session_dates: list[dt.date],
) -> dict[dt.datetime, dict[str, str]]:
    cik_to_symbol = {cik: symbol for cik, symbol in bridge_rows if symbol}
    cik_to_symbol.update({cik: symbol for cik, symbol in master_rows if symbol})
    roster = ActivistRoster(name_fragments=_ACTIVIST_FRAGMENTS)
    breaks: dict[dt.datetime, dict[str, str]] = defaultdict(dict)
    for row in stake_rows:
        if row.subject_cik not in cik_to_symbol or not roster.matches(
            cik=row.filed_by_cik, name=row.filed_by_name
        ):
            continue
        reason = None
        form = (row.form or "").upper()
        if "13G" in form:
            reason = "converted_to_13g"
        elif "13D/A" in form and row.percent_of_class is not None and row.percent_of_class <= 0.5:
            reason = "stake_exit"
        if reason is None:
            continue
        session = _session_for_signal(row.accepted_at, session_dates)
        if session is not None:
            breaks[session][cik_to_symbol[row.subject_cik]] = reason
    return dict(breaks)


async def main_async(args: argparse.Namespace) -> dict[str, Any]:
    class_rows, master_rows, bridge_rows, purchase_rows, stake_rows = await _load_events(args.start)
    candidates, diag = _candidates(
        class_rows,
        master_rows,
        bridge_rows,
        purchase_rows,
        stake_rows,
        start=args.start,
        sleeve=args.sleeve,
    )
    if not candidates:
        return {"error": "no candidate events", "diagnostics": diag}

    codes = sorted({c.symbol for c in candidates})
    bar_rows, fact_rows = await _load_prices(codes, args.start)
    bars: dict[str, list[StrategyBar]] = defaultdict(list)
    for code, d, o, h, low, cl, v, adjusted_close in bar_rows:
        if None in (o, h, low, cl) or min(o, h, low, cl) <= 0:
            continue
        adjustment = adjusted_close / cl if adjusted_close is not None and cl > 0 else 1.0
        bars[code].append(
            StrategyBar(
                date=d,
                open=o * adjustment,
                high=h * adjustment,
                low=low * adjustment,
                close=cl * adjustment,
                volume=int(v or 0),
            )
        )
    facts = [
        FundamentalObservation(
            code=row.code,
            metric=row.metric,
            value=row.value,
            unit=row.unit,
            period_start=row.period_start,
            period_end=row.period_end,
            period_type=row.period_type,
            known_at=row.known_at,
            accession_number=row.accession_number,
            concept_priority=_CONCEPT_PRIORITY.get(
                (row.metric, row.taxonomy, row.source_concept),
                len(METRIC_SPECS),
            ),
        )
        for row in fact_rows
    ]

    policy = BookPolicy(
        max_position_pct=0.05,
        max_concurrent_positions=args.max_positions,
        max_half_spread_bps=args.max_half_spread_bps,
        minimum_market_cap_mn=100.0,
        time_stop_days=args.time_stop_days,
        screen_crowding=False,
        require_market_cap=False,  # spread gate is primary; cap floor applies only when known
    )

    session_dates = sorted(
        {bar.date for history in bars.values() for bar in history if bar.date >= args.start}
    )
    sessions = [dt.datetime.combine(date, dt.time.max, tzinfo=dt.UTC) for date in session_dates]
    by_session: dict[dt.datetime, list[CandidateEvent]] = defaultdict(list)
    for candidate in candidates:
        session = _session_for_signal(candidate.signal_at, session_dates)
        if session is not None:
            by_session[session].append(candidate)

    market_state_by_session: dict[dt.datetime, dict[str, CandidateMarketState]] = {}
    all_screened = []
    for sess in sessions:
        if not by_session.get(sess):
            continue
        pit_shares = point_in_time_factor_fundamentals(facts, as_of=sess)
        spreads = {
            candidate.symbol: _spread_as_of(candidate.symbol, sess.date(), bars)
            for candidate in by_session[sess]
        }
        state = {
            candidate.symbol: _market_state_on(
                candidate.symbol,
                sess.date(),
                spreads,
                bars,
                pit_shares,
            )
            for candidate in by_session[sess]
        }
        market_state_by_session[sess] = state
        all_screened += screen_candidates(by_session[sess], state, policy)

    schedule_dt, _advances = build_weight_schedule(
        sessions=sessions,
        candidates_by_session=by_session,
        market_state_by_session=market_state_by_session,
        policy=policy,
        thesis_breaks_by_session=_thesis_breaks(
            stake_rows,
            master_rows=master_rows,
            bridge_rows=bridge_rows,
            session_dates=session_dates,
        ),
        emit_unchanged=False,
    )
    schedule: dict[dt.date, dict[str, float]] = {
        w.date(): weights for w, weights in schedule_dt.items()
    }
    held = {s for w in schedule.values() for s in w}
    if not held:
        return {
            "error": "no position ever cleared the gates",
            "diagnostics": diag,
            "rejections": rejection_summary(all_screened),
        }

    securities = [
        StrategySecurity(code=code, bars=[b for b in bars[code] if b.date >= args.start])
        for code in held
        if len(bars.get(code, [])) >= 30
    ]
    strategy_key = "us_insider_cluster_v1" if args.sleeve == "insider" else "us_activist_13d_v1"
    cost_tiered = run_cost_tiered_backtest(
        market="US",
        strategy_key=strategy_key,
        securities=securities,
        weight_schedule=schedule,
        execution_timing="next_close",
        benchmark_series=await _load_benchmark(args.start),
    )
    result = cost_tiered.primary
    navs = [p.nav for p in result.equity_curve]
    returns = [navs[i] / navs[i - 1] - 1 for i in range(1, len(navs)) if navs[i - 1] > 0]
    dsr = deflated_sharpe_ratio(returns, num_trials=args.trials)
    m = result.metrics[0]

    return {
        "window": {"start": str(args.start), "sessions_traded": len(navs)},
        "diagnostics": diag,
        "strategy_key": strategy_key,
        "book": {
            "distinct_names_held": len(held),
            "rebalance_days": len(schedule),
            "trades": len(result.trades),
            "net_return_pct": round((result.final_nav / result.initial_capital - 1) * 100, 2),
            "sharpe": m.sharpe,
            "max_drawdown_pct": m.max_drawdown_pct,
            "deflated_sharpe": round(dsr.deflated_sharpe, 4) if dsr else None,
            "clears_overfitting_bar": dsr.passes if dsr else None,
        },
        "rejections": rejection_summary(all_screened),
        "cost_stress": cost_tiered.model_dump(mode="json", exclude={"primary"}),
        "caveats": [
            "Crowding screen DISABLED: no short-interest-vs-float feed. Book ran two of three gates.",
            "Market-cap floor is secondary: applied where shares data exists (~50% coverage), spread gate primary.",
            "Market-relative comparison uses the independently loaded SPY adjusted-close series.",
            "Activist roster is a hand-curated allow-list; coverage of the true activist set is partial.",
        ],
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", type=dt.date.fromisoformat, default=dt.date(2021, 7, 1))
    p.add_argument("--max-positions", type=int, default=20)
    p.add_argument("--max-half-spread-bps", type=float, default=100.0)
    p.add_argument("--time-stop-days", type=int, default=365)
    p.add_argument("--trials", type=int, default=1)
    p.add_argument(
        "--sleeve",
        choices=["insider", "activist"],
        default="activist",
        help="the sleeves are separate preregistered hypotheses and cannot be pooled",
    )
    args = p.parse_args()
    json.dump(asyncio.run(main_async(args)), sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
