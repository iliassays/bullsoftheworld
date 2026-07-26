"""Causal daily Keltner-channel momentum research.

Signals form only after a completed close. Entry and exit decisions fill at the next session open.
This module is pure research code: it does not create Atlas targets, decisions, or paper trades.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Literal

Direction = Literal["long", "short"]


@dataclass(frozen=True)
class KeltnerSpec:
    key: str
    ema_period: int = 20
    atr_period: int = 20
    atr_multiple: float = 2.0
    maximum_holding_sessions: int = 63
    turnover_period: int = 20
    minimum_price: float = 1.0
    minimum_average_turnover: float = 1_000_000.0
    contamination_lookback_sessions: int = 20
    maximum_close_jump: float | None = None

    def __post_init__(self) -> None:
        if (
            min(
                self.ema_period,
                self.atr_period,
                self.maximum_holding_sessions,
                self.turnover_period,
            )
            <= 0
        ):
            raise ValueError("Keltner periods must be positive")
        if self.atr_multiple <= 0:
            raise ValueError("Keltner ATR multiple must be positive")
        if min(self.minimum_price, self.minimum_average_turnover) < 0:
            raise ValueError("Keltner eligibility floors cannot be negative")

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class KeltnerBar:
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float
    raw_close: float


@dataclass(frozen=True)
class KeltnerTrade:
    code: str
    direction: Direction
    signal_date: dt.date
    entry_date: dt.date
    exit_signal_date: dt.date
    exit_date: dt.date
    signal_close: float
    entry_open: float
    exit_open: float
    middle_at_signal: float
    channel_at_signal: float
    atr_at_signal: float
    breakout_strength_atr: float
    average_turnover: float
    holding_sessions: int
    exit_reason: Literal["middle_cross", "timeout"]
    gross_return: float
    normal_return: float
    stressed_return: float
    maximum_favorable_excursion: float
    maximum_adverse_excursion: float
    entry_gap: float


@dataclass(frozen=True)
class KeltnerChannels:
    middle: tuple[float | None, ...]
    atr: tuple[float | None, ...]
    upper: tuple[float | None, ...]
    lower: tuple[float | None, ...]


def _validate_bars(bars: Iterable[KeltnerBar]) -> list[KeltnerBar]:
    ordered = sorted(bars, key=lambda item: item.date)
    if len({item.date for item in ordered}) != len(ordered):
        raise ValueError("Keltner bars must contain one row per session")
    for bar in ordered:
        values = (bar.open, bar.high, bar.low, bar.close, bar.volume, bar.raw_close)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Keltner bars require finite values")
        if min(bar.open, bar.high, bar.low, bar.close, bar.raw_close) <= 0 or bar.volume < 0:
            raise ValueError("Keltner bars require positive prices and non-negative volume")
        if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
            raise ValueError("Keltner bars contain an invalid OHLC range")
    return ordered


def _ema(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    seed_index = period - 1
    result[seed_index] = statistics.fmean(values[:period])
    alpha = 2.0 / (period + 1.0)
    for index in range(seed_index + 1, len(values)):
        previous = result[index - 1]
        assert previous is not None
        result[index] = alpha * values[index] + (1.0 - alpha) * previous
    return result


def _wilder_atr(bars: list[KeltnerBar], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(bars)
    if len(bars) < period:
        return result
    true_ranges: list[float] = []
    for index, bar in enumerate(bars):
        if index == 0:
            true_ranges.append(bar.high - bar.low)
        else:
            previous_close = bars[index - 1].close
            true_ranges.append(
                max(
                    bar.high - bar.low,
                    abs(bar.high - previous_close),
                    abs(bar.low - previous_close),
                )
            )
    seed_index = period - 1
    result[seed_index] = statistics.fmean(true_ranges[:period])
    for index in range(seed_index + 1, len(bars)):
        previous = result[index - 1]
        assert previous is not None
        result[index] = (previous * (period - 1) + true_ranges[index]) / period
    return result


def keltner_channels(
    bars: Iterable[KeltnerBar],
    spec: KeltnerSpec,
) -> KeltnerChannels:
    ordered = _validate_bars(bars)
    middle = _ema([bar.close for bar in ordered], spec.ema_period)
    atr = _wilder_atr(ordered, spec.atr_period)
    upper = [
        None if center is None or width is None else center + spec.atr_multiple * width
        for center, width in zip(middle, atr, strict=True)
    ]
    lower = [
        None if center is None or width is None else center - spec.atr_multiple * width
        for center, width in zip(middle, atr, strict=True)
    ]
    return KeltnerChannels(
        middle=tuple(middle),
        atr=tuple(atr),
        upper=tuple(upper),
        lower=tuple(lower),
    )


def _average_turnover(
    bars: list[KeltnerBar],
    signal_index: int,
    window: int,
) -> float | None:
    start = signal_index - window + 1
    if start < 0:
        return None
    return statistics.fmean(bar.raw_close * bar.volume for bar in bars[start : signal_index + 1])


def _has_contamination(
    bars: list[KeltnerBar],
    *,
    start: int,
    end: int,
    maximum_jump: float | None,
) -> bool:
    if maximum_jump is None:
        return False
    start = max(1, start)
    end = min(end, len(bars) - 1)
    return any(
        abs(bars[index].raw_close / bars[index - 1].raw_close - 1.0) > maximum_jump
        for index in range(start, end + 1)
    )


def _net_return(
    direction: Direction,
    entry_open: float,
    exit_open: float,
    one_way_cost: float,
) -> float:
    if direction == "long":
        entry_fill = entry_open * (1.0 + one_way_cost)
        exit_fill = exit_open * (1.0 - one_way_cost)
        return exit_fill / entry_fill - 1.0
    entry_fill = entry_open * (1.0 - one_way_cost)
    exit_fill = exit_open * (1.0 + one_way_cost)
    return 1.0 - exit_fill / entry_fill


def _excursions(
    direction: Direction,
    entry_open: float,
    bars: list[KeltnerBar],
    entry_index: int,
    exit_index: int,
) -> tuple[float, float]:
    held = bars[entry_index:exit_index]
    if direction == "long":
        favorable = max([entry_open, *(bar.high for bar in held)]) / entry_open - 1.0
        adverse = min([entry_open, *(bar.low for bar in held)]) / entry_open - 1.0
        return favorable, adverse
    favorable = 1.0 - min([entry_open, *(bar.low for bar in held)]) / entry_open
    adverse = 1.0 - max([entry_open, *(bar.high for bar in held)]) / entry_open
    return favorable, adverse


def scan_keltner_trades(
    code: str,
    bars: Iterable[KeltnerBar],
    *,
    spec: KeltnerSpec,
    direction: Direction,
    normal_one_way_cost: float,
    stressed_one_way_cost: float,
) -> list[KeltnerTrade]:
    """Return completed, non-overlapping trades for one security."""
    ordered = _validate_bars(bars)
    channels = keltner_channels(ordered, spec)
    trades: list[KeltnerTrade] = []
    minimum_index = max(spec.ema_period, spec.atr_period)
    index = minimum_index
    while index < len(ordered) - 1:
        current_center = channels.middle[index]
        previous_center = channels.middle[index - 1]
        current_atr = channels.atr[index]
        current_channel = channels.upper[index] if direction == "long" else channels.lower[index]
        previous_channel = (
            channels.upper[index - 1] if direction == "long" else channels.lower[index - 1]
        )
        if (
            current_center is None
            or previous_center is None
            or current_atr is None
            or current_channel is None
            or previous_channel is None
            or current_atr <= 0
        ):
            index += 1
            continue
        crossed = (
            ordered[index].close > current_channel and ordered[index - 1].close <= previous_channel
            if direction == "long"
            else ordered[index].close < current_channel
            and ordered[index - 1].close >= previous_channel
        )
        if not crossed:
            index += 1
            continue

        turnover = _average_turnover(ordered, index, spec.turnover_period)
        if (
            turnover is None
            or turnover < spec.minimum_average_turnover
            or ordered[index].raw_close < spec.minimum_price
            or _has_contamination(
                ordered,
                start=index - spec.contamination_lookback_sessions + 1,
                end=index,
                maximum_jump=spec.maximum_close_jump,
            )
        ):
            index += 1
            continue

        entry_index = index + 1
        exit_signal_index: int | None = None
        exit_reason: Literal["middle_cross", "timeout"] = "timeout"
        final_decision_index = min(
            entry_index + spec.maximum_holding_sessions - 1,
            len(ordered) - 2,
        )
        for candidate in range(entry_index, final_decision_index + 1):
            center = channels.middle[candidate]
            if center is None:
                continue
            crossed_middle = (
                ordered[candidate].close < center
                if direction == "long"
                else ordered[candidate].close > center
            )
            if crossed_middle:
                exit_signal_index = candidate
                exit_reason = "middle_cross"
                break
        if exit_signal_index is None:
            requested_timeout = entry_index + spec.maximum_holding_sessions - 1
            if requested_timeout >= len(ordered) - 1:
                break
            exit_signal_index = requested_timeout
        exit_index = exit_signal_index + 1

        if _has_contamination(
            ordered,
            start=index - spec.contamination_lookback_sessions + 1,
            end=exit_signal_index,
            maximum_jump=spec.maximum_close_jump,
        ):
            index = exit_index
            continue

        entry_open = ordered[entry_index].open
        exit_open = ordered[exit_index].open
        gross = (
            exit_open / entry_open - 1.0 if direction == "long" else 1.0 - exit_open / entry_open
        )
        favorable, adverse = _excursions(
            direction,
            entry_open,
            ordered,
            entry_index,
            exit_index,
        )
        strength = (
            (ordered[index].close - current_channel) / current_atr
            if direction == "long"
            else (current_channel - ordered[index].close) / current_atr
        )
        trades.append(
            KeltnerTrade(
                code=code,
                direction=direction,
                signal_date=ordered[index].date,
                entry_date=ordered[entry_index].date,
                exit_signal_date=ordered[exit_signal_index].date,
                exit_date=ordered[exit_index].date,
                signal_close=ordered[index].close,
                entry_open=entry_open,
                exit_open=exit_open,
                middle_at_signal=current_center,
                channel_at_signal=current_channel,
                atr_at_signal=current_atr,
                breakout_strength_atr=strength,
                average_turnover=turnover,
                holding_sessions=exit_index - entry_index,
                exit_reason=exit_reason,
                gross_return=gross,
                normal_return=_net_return(
                    direction,
                    entry_open,
                    exit_open,
                    normal_one_way_cost,
                ),
                stressed_return=_net_return(
                    direction,
                    entry_open,
                    exit_open,
                    stressed_one_way_cost,
                ),
                maximum_favorable_excursion=favorable,
                maximum_adverse_excursion=adverse,
                entry_gap=entry_open / ordered[index].close - 1.0,
            )
        )
        index = exit_index
    return trades
