"""Point-in-time DSE edge research primitives.

The module intentionally contains no database access. Callers supply each instrument's genuine
observation window and a DSEX close series. Signals form after a completed close and may execute no
earlier than the next available session open.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from collections import deque
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class EdgeBar:
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class EdgeSpec:
    key: Literal[
        "deep_reclaim",
        "panic_reclaim",
        "activity_reclaim",
        "regime_limit_continuation",
    ]
    name: str
    holding_sessions: int
    stop_loss: float
    take_profit: float
    minimum_lookback: int = 60
    cooldown_sessions: int = 20


@dataclass(frozen=True)
class ExecutionPolicy:
    fee_rate: float = 0.004
    slippage_rate: float = 0.0025
    minimum_trailing_value: float = 5_000_000
    maximum_adv_participation: float = 0.02
    assumed_capital: float = 1_000_000
    target_position_weight: float = 0.10


@dataclass(frozen=True)
class SignalPolicy:
    maximum_drawdown: float = -0.40
    maximum_range_position: float = 0.15
    reclaim_sessions: int = 5


@dataclass(frozen=True)
class EdgeSignal:
    strategy: str
    code: str
    signal_index: int
    signal_date: dt.date
    entry_index: int
    entry_date: dt.date
    score: float
    trailing_value: float
    evidence: tuple[str, ...]


DEFAULT_EXECUTION_POLICY = ExecutionPolicy()
DEFAULT_SIGNAL_POLICY = SignalPolicy()


SPECS: dict[str, EdgeSpec] = {
    "deep_reclaim": EdgeSpec(
        key="deep_reclaim",
        name="Deep washout five-session reclaim",
        holding_sessions=63,
        stop_loss=-0.10,
        take_profit=0.25,
    ),
    "panic_reclaim": EdgeSpec(
        key="panic_reclaim",
        name="Capitulation then five-session reclaim",
        holding_sessions=63,
        stop_loss=-0.10,
        take_profit=0.25,
    ),
    "activity_reclaim": EdgeSpec(
        key="activity_reclaim",
        name="High-participation deep reclaim",
        holding_sessions=40,
        stop_loss=-0.08,
        take_profit=0.20,
    ),
    "regime_limit_continuation": EdgeSpec(
        key="regime_limit_continuation",
        name="Up-regime high-activity limit continuation",
        holding_sessions=5,
        stop_loss=-0.07,
        take_profit=0.12,
        minimum_lookback=60,
        cooldown_sessions=10,
    ),
}


def _rolling_extreme(values: list[float], window: int, *, maximum: bool) -> list[float]:
    queue: deque[int] = deque()
    result = [0.0] * len(values)
    for index, value in enumerate(values):
        while queue and (
            values[queue[-1]] <= value if maximum else values[queue[-1]] >= value
        ):
            queue.pop()
        queue.append(index)
        while queue and queue[0] <= index - window:
            queue.popleft()
        result[index] = values[queue[0]]
    return result


def _trailing_mean(values: list[float], window: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    running = 0.0
    for index, value in enumerate(values):
        if index >= window:
            result[index] = running / window
        running += value
        if index >= window:
            running -= values[index - window]
    return result


def _trailing_median(values: list[float], window: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    for index in range(window, len(values)):
        result[index] = statistics.median(values[index - window : index])
    return result


def _close_location(bar: EdgeBar) -> float:
    spread = bar.high - bar.low
    return (bar.close - bar.low) / spread if spread > 0 else 0.5


def _suspicious_gap(returns: list[float | None], index: int, lookback: int = 20) -> bool:
    start = max(1, index - lookback + 1)
    return any(value is not None and abs(value) > 0.35 for value in returns[start : index + 1])


def _market_regime(
    market_closes: dict[dt.date, float],
) -> dict[dt.date, tuple[bool, float | None, float | None]]:
    dates = sorted(market_closes)
    closes = [market_closes[date] for date in dates]
    result: dict[dt.date, tuple[bool, float | None, float | None]] = {}
    for index, date in enumerate(dates):
        sma_50 = statistics.fmean(closes[index - 49 : index + 1]) if index >= 49 else None
        return_20 = closes[index] / closes[index - 20] - 1 if index >= 20 else None
        result[date] = (
            sma_50 is not None
            and return_20 is not None
            and closes[index] > sma_50
            and return_20 > 0,
            sma_50,
            return_20,
        )
    return result


def _signal_at(
    *,
    spec: EdgeSpec,
    bars: list[EdgeBar],
    index: int,
    returns: list[float | None],
    volume_ratios: list[float | None],
    rolling_high: list[float],
    rolling_low: list[float],
    regime: dict[dt.date, tuple[bool, float | None, float | None]],
    signal_policy: SignalPolicy,
) -> tuple[float, tuple[str, ...]] | None:
    bar = bars[index]
    if bar.close <= 0 or rolling_high[index] <= rolling_low[index]:
        return None
    if _suspicious_gap(returns, index):
        return None

    drawdown = bar.close / rolling_high[index] - 1
    range_position = (bar.close - rolling_low[index]) / (
        rolling_high[index] - rolling_low[index]
    )
    reclaimed = index >= signal_policy.reclaim_sessions and bar.close > max(
        item.high for item in bars[index - signal_policy.reclaim_sessions : index]
    )
    volume_ratio = volume_ratios[index] or 0.0
    close_location = _close_location(bar)

    if (
        spec.key in {"deep_reclaim", "panic_reclaim", "activity_reclaim"}
        and (
            drawdown > signal_policy.maximum_drawdown
            or range_position > signal_policy.maximum_range_position
            or not reclaimed
        )
    ):
        return None

    if spec.key == "deep_reclaim":
        return (
            abs(drawdown) * 100 + max(volume_ratio, 0.0),
            (
                f"drawdown={drawdown:.1%}",
                f"range_position={range_position:.1%}",
                f"close_above_prior_{signal_policy.reclaim_sessions}d_high",
            ),
        )

    if spec.key == "panic_reclaim":
        panic_ratios = []
        for candidate in range(max(20, index - 10), index):
            candidate_return = returns[candidate]
            candidate_ratio = volume_ratios[candidate]
            if (
                candidate_return is not None
                and candidate_return <= -0.04
                and candidate_ratio is not None
                and candidate_ratio >= 1.8
                and _close_location(bars[candidate]) <= 0.50
            ):
                panic_ratios.append(candidate_ratio)
        if not panic_ratios:
            return None
        panic_ratio = max(panic_ratios)
        return (
            abs(drawdown) * 100 + panic_ratio * 4,
            (
                f"drawdown={drawdown:.1%}",
                f"panic_volume={panic_ratio:.2f}x",
                f"close_above_prior_{signal_policy.reclaim_sessions}d_high",
            ),
        )

    if spec.key == "activity_reclaim":
        if volume_ratio < 1.5 or close_location < 0.65:
            return None
        return (
            abs(drawdown) * 100 + volume_ratio * 5 + close_location * 5,
            (
                f"drawdown={drawdown:.1%}",
                f"trigger_volume={volume_ratio:.2f}x",
                f"close_location={close_location:.0%}",
            ),
        )

    if spec.key == "regime_limit_continuation":
        day_return = returns[index]
        market_up = regime.get(bar.date, (False, None, None))[0]
        prior_high = max(item.high for item in bars[index - 20 : index])
        if not (
            day_return is not None
            and day_return >= 0.08
            and volume_ratio >= 2.0
            and close_location >= 0.75
            and bar.close > prior_high
            and market_up
        ):
            return None
        return (
            day_return * 100 + volume_ratio * 2 + close_location * 2,
            (
                f"day_return={day_return:.1%}",
                f"volume={volume_ratio:.2f}x",
                "DSEX_up_regime",
            ),
        )
    raise ValueError(f"Unknown DSE edge spec: {spec.key}")


def generate_signals(
    *,
    by_code: dict[str, list[EdgeBar]],
    market_closes: dict[dt.date, float],
    spec: EdgeSpec,
    policy: ExecutionPolicy = DEFAULT_EXECUTION_POLICY,
    signal_policy: SignalPolicy = DEFAULT_SIGNAL_POLICY,
) -> list[EdgeSignal]:
    """Generate close-confirmed signals with dynamic liquidity and genuine coverage windows."""

    signals: list[EdgeSignal] = []
    regime = _market_regime(market_closes)
    for code, unordered in by_code.items():
        bars = sorted(unordered, key=lambda item: item.date)
        if len(bars) <= spec.minimum_lookback + 1:
            continue
        closes = [bar.close for bar in bars]
        volumes = [float(bar.volume) for bar in bars]
        turnovers = [bar.close * bar.volume for bar in bars]
        returns: list[float | None] = [None]
        returns.extend(
            closes[index] / closes[index - 1] - 1 if closes[index - 1] > 0 else None
            for index in range(1, len(closes))
        )
        average_volume = _trailing_mean(volumes, 20)
        median_turnover = _trailing_median(turnovers, 20)
        volume_ratios = [
            volume / average if average is not None and average > 0 else None
            for volume, average in zip(volumes, average_volume, strict=True)
        ]
        rolling_high = _rolling_extreme([bar.high for bar in bars], 252, maximum=True)
        rolling_low = _rolling_extreme([bar.low for bar in bars], 252, maximum=False)
        last_signal = -spec.cooldown_sessions

        for index in range(spec.minimum_lookback, len(bars) - 1):
            trailing_value = median_turnover[index]
            if trailing_value is None or trailing_value < policy.minimum_trailing_value:
                continue
            if index - last_signal < spec.cooldown_sessions:
                continue
            detected = _signal_at(
                spec=spec,
                bars=bars,
                index=index,
                returns=returns,
                volume_ratios=volume_ratios,
                rolling_high=rolling_high,
                rolling_low=rolling_low,
                regime=regime,
                signal_policy=signal_policy,
            )
            if detected is None:
                continue
            score, evidence = detected
            entry_index = index + 1
            signals.append(
                EdgeSignal(
                    strategy=spec.key,
                    code=code,
                    signal_index=index,
                    signal_date=bars[index].date,
                    entry_index=entry_index,
                    entry_date=bars[entry_index].date,
                    score=score,
                    trailing_value=trailing_value,
                    evidence=evidence,
                )
            )
            last_signal = index
    return sorted(signals, key=lambda item: (item.signal_date, -item.score, item.code))


def limit_locked_entry(signal_bar: EdgeBar, entry_bar: EdgeBar) -> bool:
    gap = entry_bar.open / signal_bar.close - 1 if signal_bar.close > 0 else 0.0
    intraday_range = (
        (entry_bar.high - entry_bar.low) / entry_bar.open if entry_bar.open > 0 else math.inf
    )
    return gap >= 0.075 and intraday_range <= 0.002
