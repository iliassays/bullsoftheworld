"""Read-only production-server audit for preregistered DSE native-edge hypotheses.

This file is designed to run from a temporary server directory. The two local quality modules are
loaded explicitly beside it so the diagnostic can use un-deployed research code without modifying
the production application checkout.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import importlib.util
import json
import statistics
import sys
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlalchemy import text

from bulls.analytics.dse_edge_backtest import (
    evaluate_signals,
    simulate_portfolio,
    split_outcomes,
    summarize_outcomes,
)
from bulls.analytics.dse_edges import (
    SPECS,
    EdgeBar,
    EdgeSignal,
    EdgeSpec,
    ExecutionPolicy,
    generate_signals,
)
from bulls.core.db import get_sessionmaker

START = dt.date(2025, 1, 1)
TRAIN_END = dt.date(2025, 7, 1)
VALIDATION_END = dt.date(2026, 1, 1)
BASE_EXECUTION = ExecutionPolicy(
    assumed_capital=10_000_000,
    target_position_weight=0.085,
)
STRESS_EXECUTION = ExecutionPolicy(
    assumed_capital=10_000_000,
    target_position_weight=0.085,
    slippage_rate=0.0075,
)

FROZEN_SPECIFICATION = {
    "signal_start": START.isoformat(),
    "train_end": TRAIN_END.isoformat(),
    "validation_end": VALIDATION_END.isoformat(),
    "capital_bdt": 10_000_000,
    "position_weight": 0.085,
    "maximum_positions": 10,
    "maximum_adv_participation": 0.02,
    "base_fee_each_side": 0.004,
    "base_slippage_each_side": 0.0025,
    "stress_slippage_each_side": 0.0075,
    "earnings": {"minimum_growth": 0.25, "hold": 20, "stop": -0.10, "target": 0.25},
    "dividend": {
        "minimum_point_increase": 2.0,
        "minimum_relative_increase": 0.20,
        "minimum_initiation": 5.0,
        "hold": 20,
        "stop": -0.08,
        "target": 0.20,
    },
    "insider_buy": {"hold": 20, "stop": -0.10, "target": 0.25},
    "leader_pullback": {
        "return_126": 0.20,
        "relative_strength_126": 0.10,
        "pullback_min": -0.07,
        "pullback_max": -0.01,
        "ema20_extension": 0.05,
        "cooldown": 20,
        "hold": 40,
        "stop": -0.08,
        "target": 0.20,
    },
}


def _load_local_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_quality_modules():
    root = Path(__file__).resolve().parent
    package_root = root.parent / "packages" / "analytics" / "src" / "bulls" / "analytics"
    universe_path = root / "dse_quality_universe.py"
    portfolio_path = root / "dse_quality_portfolio.py"
    if not universe_path.exists():
        universe_path = package_root / "dse_quality_universe.py"
    if not portfolio_path.exists():
        portfolio_path = package_root / "dse_quality_portfolio.py"
    universe = _load_local_module(
        "bulls.analytics.dse_quality_universe",
        universe_path,
    )
    portfolio = _load_local_module(
        "bulls.analytics.dse_quality_portfolio",
        portfolio_path,
    )
    return universe, portfolio


async def _load_server_data() -> dict[str, Any]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        await session.execute(text("SELECT set_config('app.tenant_id', 'bullsofdhaka', true)"))
        await session.execute(text("SET LOCAL statement_timeout = '10min'"))
        securities = (
            (
                await session.execute(
                    text(
                        """
                    SELECT s.code, COALESCE(s.sector, p.sector, 'Unclassified') AS sector,
                           COALESCE(s.category, p.market_category, '') AS category,
                           s.data_status, s.research_status
                    FROM symbols s
                    JOIN company_profiles p ON p.market = s.market AND p.code = s.code
                    WHERE s.market = 'DSE' AND s.is_active IS TRUE AND s.is_hidden IS FALSE
                      AND p.instrument_type = 'Equity'
                    ORDER BY s.code
                    """
                    )
                )
            )
            .mappings()
            .all()
        )
        codes = [row["code"] for row in securities]
        bars = (
            (
                await session.execute(
                    text(
                        """
                    SELECT code, date, open, high, low, close, volume
                    FROM daily_bars
                    WHERE market = 'DSE' AND code = ANY(:codes) AND date >= DATE '2024-06-27'
                    ORDER BY code, date
                    """
                    ),
                    {"codes": codes},
                )
            )
            .mappings()
            .all()
        )
        market = (
            (
                await session.execute(
                    text(
                        """
                    SELECT date, dsex FROM market_summary
                    WHERE market = 'DSE' AND dsex IS NOT NULL AND date >= DATE '2024-06-27'
                    ORDER BY date
                    """
                    )
                )
            )
            .mappings()
            .all()
        )
        announcements = (
            (
                await session.execute(
                    text(
                        """
                    SELECT code, published_at, category, strength, headline, body, details
                    FROM announcements
                    WHERE market = 'DSE' AND published_at >= DATE '2024-07-01'
                    ORDER BY published_at, code, id
                    """
                    )
                )
            )
            .mappings()
            .all()
        )
        financials = (
            (
                await session.execute(
                    text(
                        """
                    SELECT code, fiscal_year, eps, nav_per_share
                    FROM company_financials
                    WHERE market = 'DSE' AND code = ANY(:codes)
                    ORDER BY code, fiscal_year
                    """
                    ),
                    {"codes": codes},
                )
            )
            .mappings()
            .all()
        )
        dividends = (
            (
                await session.execute(
                    text(
                        """
                    SELECT code, year, cash_pct
                    FROM company_dividends
                    WHERE market = 'DSE' AND code = ANY(:codes)
                    ORDER BY code, year
                    """
                    ),
                    {"codes": codes},
                )
            )
            .mappings()
            .all()
        )
        shadow = (
            (
                await session.execute(
                    text(
                        """
                    SELECT p.id::text AS portfolio_id, p.strategy_key, p.name, p.status,
                           p.initial_capital, p.inception_date, s.as_of_date, s.session_number,
                           s.nav, s.benchmark_nav, s.drawdown_pct, s.gross_exposure_pct,
                           s.cumulative_fees
                    FROM research_shadow_portfolios p
                    LEFT JOIN research_shadow_snapshots s ON s.portfolio_id = p.id
                    WHERE p.market = 'DSE'
                    ORDER BY p.strategy_key, p.inception_date, s.as_of_date
                    """
                    )
                )
            )
            .mappings()
            .all()
        )
        hedge_snapshots = (
            (
                await session.execute(
                    text(
                        """
                    SELECT as_of_date, strategy, payload -> 'stats' AS stats,
                           payload -> 'meta' AS meta,
                           payload -> 'curve' -> 0 ->> 0 AS curve_start,
                           payload -> 'curve'
                             -> (jsonb_array_length(payload -> 'curve') - 1)
                             ->> 0 AS curve_end
                    FROM hedge_track_record_snapshots
                    WHERE market = 'DSE'
                    ORDER BY as_of_date DESC
                    """
                    )
                )
            )
            .mappings()
            .all()
        )
        remembered_hedge_signals = (
            (
                await session.execute(
                    text(
                        """
                    SELECT code, count(*) AS signals, min(signal_date) AS first_signal,
                           max(signal_date) AS last_signal,
                           count(*) FILTER (WHERE status <> 'open') AS resolved,
                           avg(result_pct) FILTER (WHERE result_pct IS NOT NULL)
                             AS avg_resolved_result_pct
                    FROM hedge_signals
                    WHERE market = 'DSE' AND signal_date >= DATE '2025-01-01'
                      AND code = ANY(:remembered_codes)
                    GROUP BY code
                    ORDER BY code
                    """
                    ),
                    {"remembered_codes": ["BXPHARMA", "BRACBANK", "SQURPHARMA"]},
                )
            )
            .mappings()
            .all()
        )
        hedge_signal_summary = (
            (
                await session.execute(
                    text(
                        """
                    SELECT strategy, count(*) AS signals,
                           count(*) FILTER (WHERE status <> 'open') AS resolved,
                           count(*) FILTER (WHERE status = 'open') AS open,
                           avg(result_pct) FILTER (WHERE result_pct IS NOT NULL)
                             AS avg_resolved_result_pct
                    FROM hedge_signals
                    WHERE market = 'DSE' AND signal_date >= DATE '2025-01-01'
                    GROUP BY strategy
                    ORDER BY strategy
                    """
                    )
                )
            )
            .mappings()
            .all()
        )
        remembered_agent_trades = (
            (
                await session.execute(
                    text(
                        """
                    SELECT p.strategy, t.code, t.side, t.quantity, t.price, t.trade_date,
                           t.fee, t.reason
                    FROM agent_trades t
                    JOIN agent_portfolios p ON p.user_id = t.user_id
                    WHERE t.market = 'DSE' AND t.trade_date >= DATE '2025-01-01'
                      AND t.code = ANY(:remembered_codes)
                    ORDER BY t.trade_date, t.id
                    """
                    ),
                    {"remembered_codes": ["BXPHARMA", "BRACBANK", "SQURPHARMA"]},
                )
            )
            .mappings()
            .all()
        )
    return {
        "securities": securities,
        "bars": bars,
        "market": market,
        "announcements": announcements,
        "financials": financials,
        "dividends": dividends,
        "shadow": shadow,
        "hedge_snapshots": hedge_snapshots,
        "remembered_hedge_signals": remembered_hedge_signals,
        "hedge_signal_summary": hedge_signal_summary,
        "remembered_agent_trades": remembered_agent_trades,
    }


def _bar_panel(rows) -> dict[str, list[EdgeBar]]:
    result: dict[str, list[EdgeBar]] = defaultdict(list)
    for row in rows:
        result[row["code"]].append(
            EdgeBar(
                date=row["date"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
            )
        )
    return dict(result)


def _event_signal(
    *,
    strategy: str,
    code: str,
    event_date: dt.date,
    score: float,
    evidence: tuple[str, ...],
    by_code: dict[str, list[EdgeBar]],
) -> EdgeSignal | None:
    bars = by_code.get(code, [])
    dates = [bar.date for bar in bars]
    entry_index = bisect_right(dates, event_date)
    signal_index = entry_index - 1
    if signal_index < 20 or entry_index >= len(bars):
        return None
    trailing = statistics.median(
        bar.close * bar.volume for bar in bars[signal_index - 19 : signal_index + 1]
    )
    if trailing < BASE_EXECUTION.minimum_trailing_value:
        return None
    return EdgeSignal(
        strategy=strategy,
        code=code,
        signal_index=signal_index,
        signal_date=bars[signal_index].date,
        entry_index=entry_index,
        entry_date=bars[entry_index].date,
        score=score,
        trailing_value=trailing,
        evidence=(f"announcement_date={event_date.isoformat()}", *evidence),
    )


def _earnings_signals(rows, by_code, valid_codes: set[str]) -> list[EdgeSignal]:
    result = []
    seen: set[tuple[str, dt.date, str]] = set()
    for row in rows:
        if row["published_at"] < START or row["code"] not in valid_codes:
            continue
        details = row["details"] if isinstance(row["details"], dict) else {}
        if row["category"] != "earnings" or not {"eps_current", "eps_prior"} <= details.keys():
            continue
        current = float(details["eps_current"])
        prior = float(details["eps_prior"])
        growth = current / prior - 1 if prior > 0 else None
        if current <= 0 or not (prior <= 0 or (growth is not None and growth >= 0.25)):
            continue
        period = str(details.get("period") or "unknown")
        key = (row["code"], row["published_at"], period)
        if key in seen:
            continue
        seen.add(key)
        score = 200 + current if prior <= 0 else min(growth or 0, 3) * 100
        signal = _event_signal(
            strategy="dse_earnings_drift_v1",
            code=row["code"],
            event_date=row["published_at"],
            score=score,
            evidence=(f"period={period}", f"eps={current}", f"prior_eps={prior}"),
            by_code=by_code,
        )
        if signal is not None:
            result.append(signal)
    return sorted(result, key=lambda item: (item.signal_date, -item.score, item.code))


def _dividend_signals(rows, by_code, valid_codes: set[str]) -> list[EdgeSignal]:
    result = []
    last_cash: dict[str, float] = {}
    seen: set[tuple[str, dt.date]] = set()
    for row in rows:
        if row["code"] not in valid_codes or row["category"] != "dividend":
            continue
        details = row["details"] if isinstance(row["details"], dict) else {}
        current: float | None = None
        if details.get("no_dividend") is True:
            current = 0.0
        elif details.get("cash_pct") is not None:
            current = float(details["cash_pct"])
        if current is None:
            continue
        previous = last_cash.get(row["code"])
        last_cash[row["code"]] = current
        if row["published_at"] < START or previous is None or current <= 0:
            continue
        initiation = previous == 0 and current >= 5
        increase = previous > 0 and current - previous >= 2 and current / previous - 1 >= 0.20
        key = (row["code"], row["published_at"])
        if not (initiation or increase) or key in seen:
            continue
        seen.add(key)
        score = current - previous + (50 if initiation else 0)
        signal = _event_signal(
            strategy="dse_dividend_revision_v1",
            code=row["code"],
            event_date=row["published_at"],
            score=score,
            evidence=(f"cash_pct={current}", f"previous_cash_pct={previous}"),
            by_code=by_code,
        )
        if signal is not None:
            result.append(signal)
    return sorted(result, key=lambda item: (item.signal_date, -item.score, item.code))


def _insider_signals(rows, by_code, valid_codes: set[str]) -> list[EdgeSignal]:
    counts: Counter[tuple[str, dt.date]] = Counter()
    for row in rows:
        headline = str(row["headline"] or "").lower()
        if (
            row["published_at"] >= START
            and row["code"] in valid_codes
            and "buy declaration" in headline
        ):
            counts[(row["code"], row["published_at"])] += 1
    result = []
    for (code, event_date), declarations in sorted(counts.items(), key=lambda item: item[0]):
        signal = _event_signal(
            strategy="dse_insider_buy_declaration_v1",
            code=code,
            event_date=event_date,
            score=float(declarations),
            evidence=(f"same_day_declarations={declarations}",),
            by_code=by_code,
        )
        if signal is not None:
            result.append(signal)
    return sorted(result, key=lambda item: (item.signal_date, -item.score, item.code))


def _ema(values: list[float], span: int) -> list[float]:
    alpha = 2 / (span + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def _market_features(
    market_closes: dict[dt.date, float],
) -> dict[dt.date, tuple[bool, float | None]]:
    dates = sorted(market_closes)
    closes = [market_closes[date] for date in dates]
    result = {}
    for index, date in enumerate(dates):
        if index < 126:
            result[date] = (False, None)
            continue
        sma50 = statistics.fmean(closes[index - 49 : index + 1])
        result[date] = (closes[index] > sma50, closes[index] / closes[index - 126] - 1)
    return result


def _leader_pullback_signals(
    by_code: dict[str, list[EdgeBar]], market_closes: dict[dt.date, float]
) -> list[EdgeSignal]:
    market = _market_features(market_closes)
    result = []
    for code, bars in by_code.items():
        closes = [bar.close for bar in bars]
        volumes = [bar.volume for bar in bars]
        ema20 = _ema(closes, 20)
        last_signal = -20
        for index in range(126, len(bars) - 1):
            bar = bars[index]
            if bar.date < START or index - last_signal < 20:
                continue
            up_regime, market_return = market.get(bar.date, (False, None))
            if not up_regime or market_return is None:
                continue
            return_126 = bar.close / closes[index - 126] - 1
            relative = return_126 - market_return
            sma50 = statistics.fmean(closes[index - 49 : index + 1])
            sma126 = statistics.fmean(closes[index - 125 : index + 1])
            pullback_high = max(item.high for item in bars[index - 5 : index])
            pullback = bars[index - 1].close / pullback_high - 1
            pullback_volume = statistics.fmean(volumes[index - 5 : index])
            volume20 = statistics.fmean(volumes[index - 20 : index])
            trailing_value = statistics.median(
                item.close * item.volume for item in bars[index - 20 : index]
            )
            if not (
                return_126 >= 0.20
                and relative >= 0.10
                and bar.close > sma50 > sma126
                and -0.07 <= pullback <= -0.01
                and pullback_volume < volume20
                and bar.close > max(item.high for item in bars[index - 3 : index])
                and ema20[index] <= bar.close <= ema20[index] * 1.05
                and bar.volume >= pullback_volume
                and trailing_value >= BASE_EXECUTION.minimum_trailing_value
            ):
                continue
            result.append(
                EdgeSignal(
                    strategy="dse_leader_pullback_daily_v1",
                    code=code,
                    signal_index=index,
                    signal_date=bar.date,
                    entry_index=index + 1,
                    entry_date=bars[index + 1].date,
                    score=relative * 100 + bar.volume / max(pullback_volume, 1),
                    trailing_value=trailing_value,
                    evidence=(
                        f"return_126={return_126:.4f}",
                        f"relative_126={relative:.4f}",
                        f"pullback={pullback:.4f}",
                    ),
                )
            )
            last_signal = index
    return sorted(result, key=lambda item: (item.signal_date, -item.score, item.code))


def _edge_spec(key: str, hold: int, stop: float, target: float) -> EdgeSpec:
    return EdgeSpec(
        key=key,  # type: ignore[arg-type]
        name=key,
        holding_sessions=hold,
        stop_loss=stop,
        take_profit=target,
        minimum_lookback=20,
        cooldown_sessions=20,
    )


def _summary(value) -> dict[str, Any]:
    return asdict(value)


def _edge_read(
    *,
    signals: list[EdgeSignal],
    spec: EdgeSpec,
    by_code: dict[str, list[EdgeBar]],
    market_closes: dict[dt.date, float],
    categories: dict[str, str],
) -> dict[str, Any]:
    signals = [item for item in signals if item.signal_date >= START]
    outcomes = evaluate_signals(
        signals=signals,
        by_code=by_code,
        market_closes=market_closes,
        spec=spec,
        policy=BASE_EXECUTION,
    )
    stressed = evaluate_signals(
        signals=signals,
        by_code=by_code,
        market_closes=market_closes,
        spec=spec,
        policy=STRESS_EXECUTION,
    )
    parts = split_outcomes(outcomes, train_end=TRAIN_END, validation_end=VALIDATION_END)
    stress_parts = split_outcomes(stressed, train_end=TRAIN_END, validation_end=VALIDATION_END)
    portfolio = simulate_portfolio(
        signals=signals,
        valid_outcomes=outcomes,
        by_code=by_code,
        market_closes=market_closes,
        spec=spec,
        policy=BASE_EXECUTION,
    )
    stress_portfolio = simulate_portfolio(
        signals=signals,
        valid_outcomes=stressed,
        by_code=by_code,
        market_closes=market_closes,
        spec=spec,
        policy=STRESS_EXECUTION,
    )
    outcome_by_key = {(item.code, item.signal_date): item for item in outcomes}
    ranked = sorted(outcomes, key=lambda item: item.net_return_pct)
    return {
        "raw_signals": len(signals),
        "executable_outcomes": len(outcomes),
        "signal_categories": dict(
            sorted(Counter(categories.get(s.code, "") for s in signals).items())
        ),
        "all": _summary(summarize_outcomes(outcomes)),
        "non_z": _summary(
            summarize_outcomes([item for item in outcomes if categories.get(item.code) != "Z"])
        ),
        "z_category": _summary(
            summarize_outcomes([item for item in outcomes if categories.get(item.code) == "Z"])
        ),
        "windows": {name: _summary(summarize_outcomes(items)) for name, items in parts.items()},
        "stressed_windows": {
            name: _summary(summarize_outcomes(items)) for name, items in stress_parts.items()
        },
        "portfolio": _summary(portfolio),
        "stressed_portfolio": _summary(stress_portfolio),
        "best": [asdict(item) for item in ranked[-3:][::-1]],
        "worst": [asdict(item) for item in ranked[:3]],
        "signals_not_executable_or_unmatured": sum(
            (item.code, item.signal_date) not in outcome_by_key for item in signals
        ),
    }


def _quality_read(data, by_code, market_closes, sectors):
    universe, portfolio = _load_quality_modules()
    financials: dict[str, list[Any]] = defaultdict(list)
    for row in data["financials"]:
        financials[row["code"]].append(
            universe.QualityFinancial(
                fiscal_year=int(row["fiscal_year"]),
                eps=float(row["eps"]) if row["eps"] is not None else None,
                nav_per_share=(
                    float(row["nav_per_share"]) if row["nav_per_share"] is not None else None
                ),
            )
        )
    dividends: dict[str, list[Any]] = defaultdict(list)
    for row in data["dividends"]:
        dividends[row["code"]].append(
            universe.QualityDividend(
                year=int(row["year"]),
                cash_pct=float(row["cash_pct"]) if row["cash_pct"] is not None else None,
            )
        )
    policy = portfolio.QualityPortfolioPolicy(
        target_positions=20,
        minimum_positions=10,
        gross_target_weight=0.85,
        capacity_aware_targets=True,
        maximum_position_weight=0.10,
        maximum_sector_weight=0.25,
    )
    rebalances = portfolio.build_quality_rebalances(
        by_code=by_code,
        market_closes=market_closes,
        financials=dict(financials),
        dividends=dict(dividends),
        quality_policy=universe.QualityUniversePolicy(),
        execution_policy=BASE_EXECUTION,
        portfolio_policy=policy,
        sectors=sectors,
    )

    def run(execution, start=None, end=None):
        return portfolio.simulate_quality_portfolio(
            rebalances=rebalances,
            by_code=by_code,
            market_closes=market_closes,
            execution_policy=execution,
            portfolio_policy=policy,
            signal_start=start,
            signal_end=end,
        )

    def book_summary(book):
        return {
            "start_date": book.start_date,
            "end_date": book.end_date,
            "total_return_pct": book.total_return_pct,
            "dsex_return_pct": book.benchmark_return_pct,
            "target_gross_dsex_cash_return_pct": book.cash_adjusted_benchmark_return_pct,
            "target_gross_excess_return_pct": book.cash_adjusted_excess_return_pct,
            "maximum_drawdown_pct": book.maximum_drawdown_pct,
            "average_gross_exposure_pct": book.average_gross_exposure_pct,
            "ending_gross_exposure_pct": book.ending_gross_exposure_pct,
            "buys": book.buys,
            "sells": book.sells,
            "capacity_shortfalls": book.capacity_shortfalls,
            "capacity_rejections": book.capacity_rejections,
            "locked_rejections": book.locked_rejections,
            "fees_paid": book.fees_paid,
        }

    return {
        "eligible_counts": [
            item.eligible_count for item in rebalances if item.signal_date >= START
        ],
        "target_counts": [len(item.targets) for item in rebalances if item.signal_date >= START],
        "base": book_summary(run(BASE_EXECUTION, START)),
        "stressed": book_summary(run(STRESS_EXECUTION, START)),
        "windows": {
            "train": book_summary(run(BASE_EXECUTION, START, TRAIN_END)),
            "validation": book_summary(run(BASE_EXECUTION, TRAIN_END, VALIDATION_END)),
            "test": book_summary(run(BASE_EXECUTION, VALIDATION_END)),
        },
    }


def _shadow_read(rows) -> list[dict[str, Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    portfolios: dict[str, Any] = {}
    for row in rows:
        portfolios[row["portfolio_id"]] = row
        if row["as_of_date"] is not None:
            grouped[row["portfolio_id"]].append(row)
    result = []
    for portfolio_id, meta in portfolios.items():
        snapshots = grouped[portfolio_id]
        first = snapshots[0] if snapshots else None
        last = snapshots[-1] if snapshots else None
        result.append(
            {
                "portfolio_id": portfolio_id,
                "strategy_key": meta["strategy_key"],
                "name": meta["name"],
                "status": meta["status"],
                "inception_date": meta["inception_date"],
                "snapshots": len(snapshots),
                "first_snapshot": first["as_of_date"] if first else None,
                "last_snapshot": last["as_of_date"] if last else None,
                "portfolio_return_pct": (
                    round((float(last["nav"]) / float(meta["initial_capital"]) - 1) * 100, 4)
                    if last
                    else None
                ),
                "benchmark_return_pct": (
                    round(
                        (float(last["benchmark_nav"]) / float(meta["initial_capital"]) - 1) * 100, 4
                    )
                    if last
                    else None
                ),
                "last_drawdown_pct": float(last["drawdown_pct"]) if last else None,
                "last_gross_exposure_pct": float(last["gross_exposure_pct"]) if last else None,
                "cumulative_fees": float(last["cumulative_fees"]) if last else None,
            }
        )
    return sorted(result, key=lambda item: (item["strategy_key"], item["inception_date"]))


async def main() -> None:
    data = await _load_server_data()
    by_code = _bar_panel(data["bars"])
    market_closes = {row["date"]: float(row["dsex"]) for row in data["market"]}
    categories = {row["code"]: row["category"] for row in data["securities"]}
    sectors = {row["code"]: row["sector"] for row in data["securities"]}
    valid_codes = set(categories)
    quality_codes = {
        row["code"]
        for row in data["securities"]
        if row["category"] != "Z"
        and row["data_status"] == "ready"
        and row["research_status"] in {"ready", "partial"}
    }
    quality_by_code = {code: by_code[code] for code in quality_codes if code in by_code}
    quality_sectors = {code: sectors[code] for code in quality_codes}
    latest = max(market_closes)

    reversal_signals = generate_signals(
        by_code=by_code,
        market_closes=market_closes,
        spec=SPECS["deep_reclaim"],
        policy=BASE_EXECUTION,
    )
    earnings = _earnings_signals(data["announcements"], by_code, valid_codes)
    dividend = _dividend_signals(data["announcements"], by_code, valid_codes)
    insider = _insider_signals(data["announcements"], by_code, valid_codes)
    leader = _leader_pullback_signals(by_code, market_closes)

    output = {
        "diagnostic_only": True,
        "execution_location": "production_server",
        "database_transaction": "read_only",
        "specification_sha256": hashlib.sha256(
            json.dumps(FROZEN_SPECIFICATION, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "window": {
            "signal_start": START,
            "latest_completed_session": latest,
            "train_end_exclusive": TRAIN_END,
            "validation_end_exclusive": VALIDATION_END,
        },
        "data": {
            "current_active_equities": len(valid_codes),
            "current_quality_input_equities": len(quality_codes),
            "bar_rows": len(data["bars"]),
            "bar_codes": len(by_code),
            "market_sessions": sum(START <= date <= latest for date in market_closes),
            "announcement_rows": sum(row["published_at"] >= START for row in data["announcements"]),
            "limitations": [
                "Current active-equity universe creates survivorship bias.",
                "Prices and DSEX are not adjusted for corporate actions or dividend total return.",
                "Announcement timestamps contain a date but not an intraday receipt time.",
                "Approximately eighteen months of signal history is not a full market cycle.",
            ],
        },
        "actual_shadow_books": _shadow_read(data["shadow"]),
        "legacy_reconciliation": {
            "hedge_track_record_snapshots": [dict(row) for row in data["hedge_snapshots"]],
            "remembered_hedge_signals": [dict(row) for row in data["remembered_hedge_signals"]],
            "hedge_signal_summary": [dict(row) for row in data["hedge_signal_summary"]],
            "remembered_agent_trades": [dict(row) for row in data["remembered_agent_trades"]],
        },
        "previous_reads": {
            "deep_reclaim": _edge_read(
                signals=reversal_signals,
                spec=SPECS["deep_reclaim"],
                by_code=by_code,
                market_closes=market_closes,
                categories=categories,
            ),
            "quality_value": _quality_read(
                data,
                quality_by_code,
                market_closes,
                quality_sectors,
            ),
        },
        "new_reads": {
            "dse_earnings_drift_v1": _edge_read(
                signals=earnings,
                spec=_edge_spec("dse_earnings_drift_v1", 20, -0.10, 0.25),
                by_code=by_code,
                market_closes=market_closes,
                categories=categories,
            ),
            "dse_dividend_revision_v1": _edge_read(
                signals=dividend,
                spec=_edge_spec("dse_dividend_revision_v1", 20, -0.08, 0.20),
                by_code=by_code,
                market_closes=market_closes,
                categories=categories,
            ),
            "dse_insider_buy_declaration_v1": _edge_read(
                signals=insider,
                spec=_edge_spec("dse_insider_buy_declaration_v1", 20, -0.10, 0.25),
                by_code=by_code,
                market_closes=market_closes,
                categories=categories,
            ),
            "dse_leader_pullback_daily_v1": _edge_read(
                signals=leader,
                spec=_edge_spec("dse_leader_pullback_daily_v1", 40, -0.08, 0.20),
                by_code=by_code,
                market_closes=market_closes,
                categories=categories,
            ),
        },
        "data_blocked": {
            "ownership_accumulation": (
                "Only two to five snapshots per company and no historical receipt timestamps."
            ),
            "rating_change": "Only two decoded upgrade/downgrade actions in the fixed window.",
            "intraday_trend_pullback": "Historical sampled intraday bars do not exist.",
        },
    }
    print(json.dumps(output, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    asyncio.run(main())
