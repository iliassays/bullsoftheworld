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
import datetime as dt
import json
import sys
from collections import defaultdict
from typing import Any

from sqlalchemy import distinct, select

from bulls.analytics.cost_observatory import estimate_spread
from bulls.analytics.deflated_sharpe import deflated_sharpe_ratio
from bulls.analytics.factor_sleeve import FundamentalFact, point_in_time_fundamentals
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
    StrategyBar,
    StrategySecurity,
    run_backtest,
)
from bulls.core.db import get_sessionmaker
from bulls.core.models import (
    DailyBar,
    EdgarFilingEvent,
    InsiderTransaction,
    OwnershipStakeEvent,
    SecFinancialFact,
    SecurityMaster,
)

# Documented multi-campaign activists (Phase 1/9 tier). Filer selection IS the strategy: the
# aggregate 13D universe carries no reliable edge, so this is an allow-list, not a screen.
_ACTIVIST_FRAGMENTS = (
    "elliott", "third point", "pershing square", "valueact", "starboard value", "icahn",
    "trian", "jana partners", "corvex", "sachem head", "engaged capital", "legion partners",
    "ancora", "politan", "engine capital", "carl c", "value act", "scion", "cannell",
    "barington", "land & buildings", "impactive", "inclusive capital", "sarissa",
)


async def _load_events(start: dt.date):
    """Phase 1: everything needed to decide candidates, without touching prices."""
    sm = get_sessionmaker()
    async with sm() as s:
        # Light projection for routine/opportunistic classification: the pattern lives in an
        # insider's full trade calendar, so we need every date but only the date and owner.
        class_rows = list(await s.execute(
            select(InsiderTransaction.owner_cik, InsiderTransaction.transaction_date)
            .where(InsiderTransaction.transaction_date.is_not(None))
        ))
        # CIK -> symbol bridge. The security master is the authoritative source (it resolves
        # activist 13D targets that never appear in the insider stream); the insider table's own
        # paired columns are a fallback for anything the master is missing.
        master_rows = list(await s.execute(
            select(SecurityMaster.cik, SecurityMaster.symbol)
            .where(SecurityMaster.market == "US", SecurityMaster.cik.is_not(None))
        ))
        bridge_rows = list(await s.execute(
            select(distinct(InsiderTransaction.issuer_cik), InsiderTransaction.issuer_symbol)
            .where(InsiderTransaction.issuer_symbol.is_not(None))
        ))
        # Only open-market purchases disseminated in the window can become candidates; hydrate
        # just those (a small fraction of the 1.7M rows).
        purchase_rows = list(await s.execute(
            select(
                InsiderTransaction.issuer_cik, InsiderTransaction.issuer_symbol,
                InsiderTransaction.owner_cik, InsiderTransaction.transaction_date,
                InsiderTransaction.code, InsiderTransaction.shares,
                InsiderTransaction.price_per_share, InsiderTransaction.is_10b5_1_plan,
                InsiderTransaction.is_officer, InsiderTransaction.is_director,
                InsiderTransaction.is_ten_percent_owner, EdgarFilingEvent.accepted_at,
            )
            .join(EdgarFilingEvent,
                  EdgarFilingEvent.accession_number == InsiderTransaction.accession_number)
            .where(InsiderTransaction.code == "P",
                   InsiderTransaction.transaction_date.is_not(None),
                   EdgarFilingEvent.accepted_at.is_not(None),
                   EdgarFilingEvent.accepted_at >= start - dt.timedelta(days=45))
        ))
        stake_rows = list(await s.execute(
            select(
                OwnershipStakeEvent.accession_number, OwnershipStakeEvent.subject_cik,
                OwnershipStakeEvent.subject_name, OwnershipStakeEvent.filed_by_cik,
                OwnershipStakeEvent.filed_by_name, OwnershipStakeEvent.form,
                OwnershipStakeEvent.accepted_at, OwnershipStakeEvent.percent_of_class,
            )
            .where(OwnershipStakeEvent.form.like("%13D%"),
                   OwnershipStakeEvent.accepted_at.is_not(None))
        ))
    return class_rows, master_rows, bridge_rows, purchase_rows, stake_rows


async def _load_prices(codes: list[str], start: dt.date):
    """Phase 2: bars + shares only for the names that became candidates, chunked."""
    sm = get_sessionmaker()
    bar_rows: list = []
    fact_rows: list = []
    async with sm() as s:
        for i in range(0, len(codes), 400):
            chunk = codes[i : i + 400]
            bar_rows += list(await s.execute(
                select(DailyBar.code, DailyBar.date, DailyBar.open, DailyBar.high,
                       DailyBar.low, DailyBar.close, DailyBar.volume)
                .where(DailyBar.market == "US", DailyBar.code.in_(chunk),
                       DailyBar.date >= start - dt.timedelta(days=400))
                .order_by(DailyBar.code, DailyBar.date)
            ))
            fact_rows += list(await s.execute(
                select(SecFinancialFact.code, SecFinancialFact.value,
                       SecFinancialFact.period_end, SecFinancialFact.filed_at)
                .where(SecFinancialFact.market == "US", SecFinancialFact.code.in_(chunk),
                       SecFinancialFact.metric == "shares_outstanding")
            ))
    return bar_rows, fact_rows


def _candidates(class_rows, master_rows, bridge_rows, purchase_rows, stake_rows, *, start):
    # Routine/opportunistic per insider, from the light projection.
    owner_dates: dict[int, list[dt.date]] = defaultdict(list)
    for owner_cik, txn_date in class_rows:
        owner_dates[owner_cik].append(txn_date)
    classes = {owner: classify_insider(dates) for owner, dates in owner_dates.items()}

    # Security master first (authoritative), then the insider pairs fill any gaps.
    cik_to_symbol = {cik: sym for cik, sym in bridge_rows if sym}
    cik_to_symbol.update({cik: sym for cik, sym in master_rows if sym})

    trades = [
        InsiderTrade(
            issuer_cik=r.issuer_cik, issuer_symbol=r.issuer_symbol, owner_cik=r.owner_cik,
            transaction_date=r.transaction_date, disseminated_at=r.accepted_at,
            code=r.code, shares=r.shares, price_per_share=r.price_per_share,
            is_10b5_1_plan=r.is_10b5_1_plan, is_officer=r.is_officer,
            is_director=r.is_director, is_ten_percent_owner=r.is_ten_percent_owner,
        )
        for r in purchase_rows
    ]
    purchases = [t for t in qualifying_purchases(trades, classes) if t.issuer_symbol]
    clusters = detect_clusters(purchases, window_days=30, minimum_insiders=1)
    insider_candidates = [
        CandidateEvent(
            symbol=c.issuer_symbol, issuer_cik=c.issuer_cik, kind="insider_cluster",
            signal_at=c.signal_at,
            strength=c.distinct_insiders + (0.5 if c.includes_officer_or_director else 0.0),
        )
        for c in clusters if c.issuer_symbol and c.signal_at.date() >= start
    ]

    roster = ActivistRoster(name_fragments=_ACTIVIST_FRAGMENTS)
    activist_events = [
        ActivistEvent(
            accession_number=r.accession_number, subject_cik=r.subject_cik,
            subject_name=r.subject_name, filed_by_cik=r.filed_by_cik,
            filed_by_name=r.filed_by_name, form=r.form, signal_at=r.accepted_at,
            percent_of_class=r.percent_of_class, is_amendment="/A" in (r.form or ""),
        )
        for r in stake_rows
    ]
    activist_candidates = [
        CandidateEvent(
            symbol=cik_to_symbol[e.subject_cik], issuer_cik=e.subject_cik, kind="activist_13d",
            signal_at=e.signal_at, strength=5.0,
        )
        for e in qualifying_activist_events(activist_events, roster)
        if e.subject_cik in cik_to_symbol and e.signal_at.date() >= start
    ]

    candidates = insider_candidates + activist_candidates
    diag = {
        "classified_insiders": len(classes),
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


async def main_async(args: argparse.Namespace) -> dict[str, Any]:
    class_rows, master_rows, bridge_rows, purchase_rows, stake_rows = await _load_events(args.start)
    candidates, diag = _candidates(
        class_rows, master_rows, bridge_rows, purchase_rows, stake_rows, start=args.start
    )
    if not candidates:
        return {"error": "no candidate events", "diagnostics": diag}

    codes = sorted({c.symbol for c in candidates})
    bar_rows, fact_rows = await _load_prices(codes, args.start)
    bars: dict[str, list[StrategyBar]] = defaultdict(list)
    for code, d, o, h, low, cl, v in bar_rows:
        if None in (o, h, low, cl) or min(o, h, low, cl) <= 0:
            continue
        bars[code].append(StrategyBar(date=d, open=o, high=h, low=low, close=cl, volume=int(v or 0)))
    facts = [FundamentalFact(code=c, metric="shares_outstanding", value=v, period_end=pe, filed_at=fa)
             for c, v, pe, fa in fact_rows]

    spreads: dict[str, float] = {}
    for code in codes:
        history = bars.get(code)
        if not history:
            continue
        est = estimate_spread(code, [b.high for b in history], [b.low for b in history])
        if est is not None:
            spreads[code] = est.half_spread_bps

    policy = BookPolicy(
        max_position_pct=0.05, max_concurrent_positions=args.max_positions,
        max_half_spread_bps=args.max_half_spread_bps, minimum_market_cap_mn=100.0,
        time_stop_days=args.time_stop_days, screen_crowding=False,
        require_market_cap=False,  # spread gate is primary; cap floor applies only when known
    )

    by_session: dict[dt.datetime, list[CandidateEvent]] = defaultdict(list)
    for c in candidates:
        by_session[c.signal_at].append(c)
    sessions = sorted(by_session)

    market_state_by_session: dict[dt.datetime, dict[str, CandidateMarketState]] = {}
    all_screened = []
    for sess in sessions:
        pit_shares = point_in_time_fundamentals(facts, as_of=sess.date())
        state = {c.symbol: _market_state_on(c.symbol, sess.date(), spreads, bars, pit_shares)
                 for c in by_session[sess]}
        market_state_by_session[sess] = state
        all_screened += screen_candidates(by_session[sess], state, policy)

    schedule_dt, _advances = build_weight_schedule(
        sessions=sessions, candidates_by_session=by_session,
        market_state_by_session=market_state_by_session, policy=policy,
    )
    schedule: dict[dt.date, dict[str, float]] = {w.date(): weights for w, weights in schedule_dt.items()}
    held = {s for w in schedule.values() for s in w}
    if not held:
        return {"error": "no position ever cleared the gates", "diagnostics": diag,
                "rejections": rejection_summary(all_screened)}

    securities = [
        StrategySecurity(code=code, bars=[b for b in bars[code] if b.date >= args.start])
        for code in held if len(bars.get(code, [])) >= 30
    ]
    result = run_backtest(
        market="US", strategy_key="us_breakout_v1", securities=securities,
        weight_schedule=schedule,
        half_spread_bps={c: spreads[c] for c in held if c in spreads},
    )
    navs = [p.nav for p in result.equity_curve]
    returns = [navs[i] / navs[i - 1] - 1 for i in range(1, len(navs)) if navs[i - 1] > 0]
    dsr = deflated_sharpe_ratio(returns, num_trials=args.trials)
    m = result.metrics[0]

    return {
        "window": {"start": str(args.start), "sessions_traded": len(navs)},
        "diagnostics": diag,
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
        "caveats": [
            "Crowding screen DISABLED: no short-interest-vs-float feed. Book ran two of three gates.",
            "Market-cap floor is secondary: applied where shares data exists (~50% coverage), spread gate primary.",
            "Benchmark comparison omitted: the engine benchmark is a biased arithmetic-mean series.",
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
    args = p.parse_args()
    json.dump(asyncio.run(main_async(args)), sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
