"""Pre-registered cross-sectional DSE factors built only from completed daily data.

The module has no database access. Callers provide genuine per-security observation windows,
conservatively lagged annual fundamentals, dividends, and the DSEX session calendar. Signals form
after a completed close and may execute only at the next market-session open.
"""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass
from typing import Literal

from bulls.analytics.dse_edges import EdgeBar, EdgeSignal, EdgeSpec, ExecutionPolicy

FactorKey = Literal[
    "quality_value_daily",
    "defensive_low_vol_daily",
    "momentum_daily_control",
]


@dataclass(frozen=True)
class FundamentalRecord:
    fiscal_year: int
    eps: float | None
    nav_per_share: float | None


@dataclass(frozen=True)
class DividendPoint:
    year: int
    cash_pct: float | None


@dataclass(frozen=True)
class DailyFactorSpec:
    key: FactorKey
    name: str
    holding_sessions: int
    stop_loss: float
    take_profit: float
    minimum_lookback: int = 126
    rebalance_sessions: int = 21
    maximum_selections: int = 10

    @property
    def exit_spec(self) -> EdgeSpec:
        return EdgeSpec(
            key=self.key,
            name=self.name,
            holding_sessions=self.holding_sessions,
            stop_loss=self.stop_loss,
            take_profit=self.take_profit,
            minimum_lookback=self.minimum_lookback,
            cooldown_sessions=self.holding_sessions,
        )


FACTOR_SPECS: dict[FactorKey, DailyFactorSpec] = {
    "quality_value_daily": DailyFactorSpec(
        key="quality_value_daily",
        name="Conservatively lagged quality-value",
        holding_sessions=126,
        stop_loss=-0.15,
        take_profit=0.50,
    ),
    "defensive_low_vol_daily": DailyFactorSpec(
        key="defensive_low_vol_daily",
        name="Positive-trend defensive low volatility",
        holding_sessions=63,
        stop_loss=-0.10,
        take_profit=0.20,
    ),
    "momentum_daily_control": DailyFactorSpec(
        key="momentum_daily_control",
        name="Six-minus-one-month momentum control",
        holding_sessions=63,
        stop_loss=-0.10,
        take_profit=0.20,
    ),
}


@dataclass(frozen=True)
class _FactorRow:
    code: str
    index: int
    bar: EdgeBar
    next_bar: EdgeBar
    trailing_value: float
    volatility_60: float
    momentum_6_1: float
    sma_126: float
    pe: float | None = None
    pb: float | None = None
    roe: float | None = None
    eps_growth: float | None = None
    dividend_years: float | None = None
    fiscal_year: int | None = None


def _median_trailing_value(bars: list[EdgeBar], index: int, window: int = 20) -> float | None:
    if index < window:
        return None
    return statistics.median(bar.close * bar.volume for bar in bars[index - window : index])


def _returns(bars: list[EdgeBar], start: int, end: int) -> list[float]:
    values = []
    for index in range(max(1, start), end):
        previous = bars[index - 1].close
        if previous > 0:
            values.append(bars[index].close / previous - 1)
    return values


def _has_suspicious_gap(bars: list[EdgeBar], index: int, lookback: int = 20) -> bool:
    return any(abs(value) > 0.35 for value in _returns(bars, index - lookback + 1, index + 1))


def fundamental_features(
    *,
    code: str,
    price: float,
    signal_date: dt.date,
    financials: dict[str, list[FundamentalRecord]],
    dividends: dict[str, list[DividendPoint]],
) -> tuple[float, float, float, float | None, float, int] | None:
    """Return a deliberately stale fundamental view to prevent publication lookahead.

    Exact DSE publication timestamps are not retained, so the lab uses only fiscal years no later
    than ``signal year - 2``. This is conservative and may omit usable information, but it cannot
    silently treat the immediately preceding fiscal year as known on January 1.
    """

    cutoff = signal_date.year - 2
    known = {item.fiscal_year: item for item in financials.get(code, []) if item.fiscal_year <= cutoff}
    if not known:
        return None
    fiscal_year = max(known)
    current = known[fiscal_year]
    if (
        current.eps is None
        or current.eps <= 0
        or current.nav_per_share is None
        or current.nav_per_share <= 0
        or price <= 0
    ):
        return None
    pe = price / current.eps
    pb = price / current.nav_per_share
    if not (0 < pe <= 50 and 0 < pb <= 10):
        return None
    roe = current.eps / current.nav_per_share * 100
    previous = known.get(fiscal_year - 1)
    eps_growth = (
        (current.eps - previous.eps) / abs(previous.eps) * 100
        if previous is not None and previous.eps not in (None, 0)
        else None
    )
    dividend_years = float(
        sum(
            1
            for item in dividends.get(code, [])
            if fiscal_year - 4 <= item.year <= fiscal_year
            and item.cash_pct is not None
            and item.cash_pct > 0
        )
    )
    return pe, pb, roe, eps_growth, dividend_years, fiscal_year


def _factor_row(
    *,
    code: str,
    bars: list[EdgeBar],
    index: int,
    next_market_date: dt.date,
    signal_date: dt.date,
    spec: DailyFactorSpec,
    policy: ExecutionPolicy,
    financials: dict[str, list[FundamentalRecord]],
    dividends: dict[str, list[DividendPoint]],
) -> _FactorRow | None:
    if index < spec.minimum_lookback or index + 1 >= len(bars):
        return None
    bar = bars[index]
    next_bar = bars[index + 1]
    if bar.date != signal_date or next_bar.date != next_market_date:
        return None
    trailing_value = _median_trailing_value(bars, index)
    if trailing_value is None or trailing_value < policy.minimum_trailing_value:
        return None
    if _has_suspicious_gap(bars, index):
        return None
    returns_60 = _returns(bars, index - 59, index + 1)
    if len(returns_60) < 50:
        return None
    volatility = statistics.stdev(returns_60) * (252**0.5)
    if volatility <= 0:
        return None
    prior_momentum_close = bars[index - 21].close
    old_momentum_close = bars[index - 126].close
    if min(prior_momentum_close, old_momentum_close) <= 0:
        return None
    momentum = prior_momentum_close / old_momentum_close - 1
    sma_126 = statistics.fmean(item.close for item in bars[index - 125 : index + 1])
    values: dict[str, float | int | None] = {}
    if spec.key == "quality_value_daily":
        fundamental = fundamental_features(
            code=code,
            price=bar.close,
            signal_date=signal_date,
            financials=financials,
            dividends=dividends,
        )
        if fundamental is None:
            return None
        pe, pb, roe, eps_growth, dividend_years, fiscal_year = fundamental
        values = {
            "pe": pe,
            "pb": pb,
            "roe": roe,
            "eps_growth": eps_growth,
            "dividend_years": dividend_years,
            "fiscal_year": fiscal_year,
        }
    return _FactorRow(
        code=code,
        index=index,
        bar=bar,
        next_bar=next_bar,
        trailing_value=trailing_value,
        volatility_60=volatility,
        momentum_6_1=momentum,
        sma_126=sma_126,
        **values,
    )


def _percentiles(values: dict[str, float], *, higher_is_better: bool) -> dict[str, float]:
    if not values:
        return {}
    unique = sorted(set(values.values()), reverse=not higher_is_better)
    if len(unique) == 1:
        return {code: 1.0 for code in values}
    ranks = {value: index / (len(unique) - 1) for index, value in enumerate(unique)}
    return {code: ranks[value] for code, value in values.items()}


def _quality_value_scores(rows: dict[str, _FactorRow]) -> dict[str, float]:
    pe = _percentiles({code: float(row.pe) for code, row in rows.items()}, higher_is_better=False)
    pb = _percentiles({code: float(row.pb) for code, row in rows.items()}, higher_is_better=False)
    roe = _percentiles({code: float(row.roe) for code, row in rows.items()}, higher_is_better=True)
    growth = _percentiles(
        {code: float(row.eps_growth) for code, row in rows.items() if row.eps_growth is not None},
        higher_is_better=True,
    )
    dividends = _percentiles(
        {code: float(row.dividend_years) for code, row in rows.items()},
        higher_is_better=True,
    )
    result = {}
    for code in rows:
        value = statistics.fmean((pe[code], pb[code]))
        quality_inputs = [roe[code], dividends[code]]
        if code in growth:
            quality_inputs.append(growth[code])
        result[code] = statistics.fmean((value, statistics.fmean(quality_inputs)))
    return result


def _scores(spec: DailyFactorSpec, rows: dict[str, _FactorRow]) -> dict[str, float]:
    if spec.key == "quality_value_daily":
        return _quality_value_scores(rows)
    if spec.key == "defensive_low_vol_daily":
        eligible = {
            code: row
            for code, row in rows.items()
            if row.bar.close >= row.sma_126 and row.momentum_6_1 > 0
        }
        return _percentiles(
            {code: row.volatility_60 for code, row in eligible.items()},
            higher_is_better=False,
        )
    if spec.key == "momentum_daily_control":
        return {
            code: row.momentum_6_1
            for code, row in rows.items()
            if row.bar.close >= row.sma_126 and row.momentum_6_1 > 0
        }
    raise ValueError(f"Unknown daily factor: {spec.key}")


def generate_factor_signals(
    *,
    by_code: dict[str, list[EdgeBar]],
    market_closes: dict[dt.date, float],
    financials: dict[str, list[FundamentalRecord]],
    dividends: dict[str, list[DividendPoint]],
    spec: DailyFactorSpec,
    policy: ExecutionPolicy,
) -> list[EdgeSignal]:
    """Select a bounded cross-sectional basket on fixed market-session intervals."""

    market_dates = sorted(market_closes)
    if len(market_dates) <= spec.minimum_lookback + 1:
        return []
    date_indexes = {
        code: {bar.date: index for index, bar in enumerate(sorted(bars, key=lambda item: item.date))}
        for code, bars in by_code.items()
    }
    sorted_bars = {
        code: sorted(bars, key=lambda item: item.date) for code, bars in by_code.items()
    }
    last_signal_index: dict[str, int] = {}
    signals: list[EdgeSignal] = []
    for market_index in range(
        spec.minimum_lookback,
        len(market_dates) - 1,
        spec.rebalance_sessions,
    ):
        signal_date = market_dates[market_index]
        next_market_date = market_dates[market_index + 1]
        rows: dict[str, _FactorRow] = {}
        for code, bars in sorted_bars.items():
            index = date_indexes[code].get(signal_date)
            if index is None:
                continue
            row = _factor_row(
                code=code,
                bars=bars,
                index=index,
                next_market_date=next_market_date,
                signal_date=signal_date,
                spec=spec,
                policy=policy,
                financials=financials,
                dividends=dividends,
            )
            if row is not None:
                rows[code] = row
        if len(rows) < 20:
            continue
        scores = _scores(spec, rows)
        selected = 0
        for code in sorted(scores, key=lambda item: (-scores[item], item)):
            row = rows[code]
            previous_index = last_signal_index.get(code)
            if previous_index is not None and row.index - previous_index < spec.holding_sessions:
                continue
            evidence = [
                f"trailing_value={row.trailing_value:.0f}",
                f"volatility_60={row.volatility_60:.2%}",
                f"momentum_6_1={row.momentum_6_1:.2%}",
            ]
            if spec.key == "quality_value_daily":
                evidence.extend(
                    (
                        f"pe={row.pe:.2f}",
                        f"pb={row.pb:.2f}",
                        f"roe={row.roe:.2f}",
                        f"fundamental_fy={row.fiscal_year}",
                    )
                )
            signals.append(
                EdgeSignal(
                    strategy=spec.key,
                    code=code,
                    signal_index=row.index,
                    signal_date=signal_date,
                    entry_index=row.index + 1,
                    entry_date=row.next_bar.date,
                    score=scores[code],
                    trailing_value=row.trailing_value,
                    evidence=tuple(evidence),
                )
            )
            last_signal_index[code] = row.index
            selected += 1
            if selected >= spec.maximum_selections:
                break
    return sorted(signals, key=lambda item: (item.signal_date, -item.score, item.code))
