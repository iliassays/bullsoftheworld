"""Walk-forward study for the high-volume flat-base setup.

Thresholds are selected on the first half of available DSE history and reported on the untouched
second half. Signals use only information known at that close; modeled entry is the next session's
open with 0.4% cost on entry and exit. This is an event study, not a claim of executable fills.

    uv run python scripts/flat_base_breakout_study.py
"""

from __future__ import annotations

import asyncio
import datetime as dt
import statistics
from dataclasses import dataclass, replace
from itertools import product

from portfolio_backtest import COST, _load

from bulls.analytics.flat_base import FlatBaseConfig, detect_flat_base_at

SPLIT_DATE = dt.date(2025, 7, 1)
FORWARD_DAYS = 20
COOLDOWN_DAYS = 20


@dataclass(frozen=True)
class Event:
    code: str
    signal_date: dt.date
    outcome_date: dt.date
    entry: float
    return_20d: float
    mfe_20d: float
    mae_20d: float


def _event(code, bars, signal_index: int) -> Event | None:
    entry_index = signal_index + 1
    end_index = entry_index + FORWARD_DAYS - 1
    if end_index >= len(bars):
        return None
    raw_entry = bars[entry_index].open or bars[entry_index].close
    if not raw_entry or raw_entry <= 0:
        return None
    entry = raw_entry * (1 + COST)
    window = bars[entry_index : end_index + 1]
    exit_value = window[-1].close * (1 - COST)
    best_value = max(bar.high for bar in window) * (1 - COST)
    worst_value = min(bar.low for bar in window) * (1 - COST)
    return Event(
        code=code,
        signal_date=bars[signal_index].date,
        outcome_date=window[-1].date,
        entry=entry,
        return_20d=(exit_value / entry - 1) * 100,
        mfe_20d=(best_value / entry - 1) * 100,
        mae_20d=(worst_value / entry - 1) * 100,
    )


def _flat_base_events(by_code, config: FlatBaseConfig) -> list[Event]:
    events: list[Event] = []
    for code, bars in by_code.items():
        last_signal = -COOLDOWN_DAYS
        for i in range(60, len(bars)):
            if i - last_signal < COOLDOWN_DAYS:
                continue
            setup = detect_flat_base_at(bars, i, config=config)
            if setup is None or setup.status != "confirmed_breakout_up":
                continue
            event = _event(code, bars, i)
            if event is not None:
                events.append(event)
                last_signal = i
    return events


def _control_events(by_code, config: FlatBaseConfig) -> list[Event]:
    """Generic 20-day high + volume control with the same liquidity/execution filters."""
    events: list[Event] = []
    for code, bars in by_code.items():
        last_signal = -COOLDOWN_DAYS
        for i in range(20, len(bars)):
            if i - last_signal < COOLDOWN_DAYS:
                continue
            base = bars[i - 20 : i]
            current = bars[i]
            resistance = max(bar.high for bar in base)
            average_volume = statistics.fmean(bar.volume for bar in base)
            average_turnover = statistics.fmean(bar.close * bar.volume for bar in base)
            day_range = current.high - current.low
            close_location = (current.close - current.low) / day_range if day_range > 0 else 0.5
            if not (
                current.close >= config.min_price
                and average_turnover >= config.min_average_turnover
                and resistance * (1 + config.breakout_buffer)
                < current.close
                <= resistance * (1 + config.max_breakout_extension)
                and current.volume >= config.min_breakout_volume_ratio * average_volume
                and close_location >= config.min_breakout_close_location
            ):
                continue
            event = _event(code, bars, i)
            if event is not None:
                events.append(event)
                last_signal = i
    return events


def _period(events: list[Event], validation: bool) -> list[Event]:
    if validation:
        return [event for event in events if event.signal_date >= SPLIT_DATE]
    return [
        event
        for event in events
        if event.signal_date < SPLIT_DATE and event.outcome_date < SPLIT_DATE
    ]


def _summary(events: list[Event]) -> dict[str, float]:
    if not events:
        return {"n": 0.0}
    returns = [event.return_20d for event in events]
    mfes = [event.mfe_20d for event in events]
    maes = [event.mae_20d for event in events]
    return {
        "n": float(len(events)),
        "median_20d": statistics.median(returns),
        "mean_20d": statistics.fmean(returns),
        "positive_20d": 100 * sum(value > 0 for value in returns) / len(events),
        "hit_10": 100 * sum(value >= 10 for value in mfes) / len(events),
        "hit_15": 100 * sum(value >= 15 for value in mfes) / len(events),
        "hit_20": 100 * sum(value >= 20 for value in mfes) / len(events),
        "median_mfe": statistics.median(mfes),
        "median_mae": statistics.median(maes),
    }


def _line(label: str, summary: dict[str, float]) -> str:
    if not summary.get("n"):
        return f"{label:<24} no events"
    return (
        f"{label:<24} n={summary['n']:>4.0f}  median20={summary['median_20d']:>+6.2f}%  "
        f"positive={summary['positive_20d']:>5.1f}%  hit10/15/20="
        f"{summary['hit_10']:>4.1f}/{summary['hit_15']:>4.1f}/{summary['hit_20']:>4.1f}%  "
        f"MFE/MAE={summary['median_mfe']:>+5.1f}/{summary['median_mae']:>+5.1f}%"
    )


def _forming_summary(by_code, config: FlatBaseConfig, *, validation: bool) -> dict[str, float]:
    setups = breakout_10 = move_10 = 0
    for bars in by_code.values():
        last_setup = -10
        for i in range(60, len(bars) - FORWARD_DAYS):
            date = bars[i].date
            if validation != (date >= SPLIT_DATE) or i - last_setup < 10:
                continue
            setup = detect_flat_base_at(bars, i, config=config)
            if setup is None or setup.status != "forming":
                continue
            setups += 1
            last_setup = i
            if any(
                (candidate := detect_flat_base_at(bars, j, config=config)) is not None
                and candidate.status == "confirmed_breakout_up"
                for j in range(i + 1, min(i + 11, len(bars)))
            ):
                breakout_10 += 1
            if max(bar.high for bar in bars[i + 1 : i + FORWARD_DAYS + 1]) >= bars[i].close * 1.10:
                move_10 += 1
    return {
        "n": float(setups),
        "breakout_10": 100 * breakout_10 / setups if setups else 0.0,
        "move_10": 100 * move_10 / setups if setups else 0.0,
    }


def _config_label(config: FlatBaseConfig) -> str:
    return (
        f"days={config.base_days}, depth={config.max_depth:.0%}, "
        f"vol={config.min_breakout_volume_ratio:.2f}x, dry={config.max_dry_up_ratio:.2f}x"
    )


async def _run() -> None:
    by_code, _ = await _load()
    default = FlatBaseConfig()
    configs = [
        replace(
            default,
            base_days=base_days,
            max_depth=max_depth,
            min_breakout_volume_ratio=volume_ratio,
            max_dry_up_ratio=dry_ratio,
        )
        for base_days, max_depth, volume_ratio, dry_ratio in product(
            (15, 20, 30),
            (0.10, 0.12, 0.15),
            (1.25, 1.50),
            (1.20,),
        )
    ]

    print(f"Evaluating {len(configs)} pre-declared configurations...", flush=True)
    ranked: list[tuple[float, float, int, FlatBaseConfig, list[Event]]] = []
    for config in configs:
        events = _flat_base_events(by_code, config)
        train = _summary(_period(events, validation=False))
        if train.get("n", 0) < 25:
            continue
        ranked.append(
            (
                train["median_20d"],
                train["hit_10"],
                int(train["n"]),
                config,
                events,
            )
        )
    ranked.sort(reverse=True, key=lambda row: row[:3])
    if not ranked:
        raise RuntimeError("No configuration produced enough training events")

    print(f"DSE history: train before {SPLIT_DATE}; validation on/after {SPLIT_DATE}.")
    print("Entry: next open; 0.4% each side; 20-session horizon; 20-session signal cooldown.\n")
    print("Top training configurations (validation was not used for selection):")
    for _, _, _, config, events in ranked[:8]:
        print(_line(_config_label(config), _summary(_period(events, validation=False))))

    selected = ranked[0][3]
    selected_events = ranked[0][4]
    control_events = _control_events(by_code, selected)
    print(f"\nSelected: {_config_label(selected)}")
    print(_line("flat-base train", _summary(_period(selected_events, validation=False))))
    print(_line("control train", _summary(_period(control_events, validation=False))))
    print(_line("flat-base validation", _summary(_period(selected_events, validation=True))))
    print(_line("control validation", _summary(_period(control_events, validation=True))))

    portal = FlatBaseConfig()
    portal_events = _flat_base_events(by_code, portal)
    portal_control = _control_events(by_code, portal)
    print(f"\nStrict portal candidate: {_config_label(portal)}")
    print(_line("portal train", _summary(_period(portal_events, validation=False))))
    print(_line("control train", _summary(_period(portal_control, validation=False))))
    print(_line("portal validation", _summary(_period(portal_events, validation=True))))
    print(_line("control validation", _summary(_period(portal_control, validation=True))))

    print("\nValidation stability for the five train-selected neighbors:")
    for _, _, _, config, events in ranked[:5]:
        print(_line(_config_label(config), _summary(_period(events, validation=True))))

    forming_train = _forming_summary(by_code, portal, validation=False)
    forming_validation = _forming_summary(by_code, portal, validation=True)
    print("\nEarly forming watch (deduplicated every 10 sessions):")
    for label, summary in (("train", forming_train), ("validation", forming_validation)):
        print(
            f"  {label:<10} n={summary['n']:.0f}  confirmed breakout within 10d="
            f"{summary['breakout_10']:.1f}%  reached +10% within 20d={summary['move_10']:.1f}%"
        )

    print("\nITC detections under the selected thresholds:")
    for i in range(60, len(by_code.get("ITC", []))):
        setup = detect_flat_base_at(by_code["ITC"], i, config=portal)
        if setup is not None:
            print(
                f"  {setup.as_of_date} {setup.status:<23} resistance={setup.resistance:.2f} "
                f"depth={setup.depth:.1%} volume={setup.volume_ratio:.2f}x "
                f"dry={setup.dry_up_ratio:.2f}x score={setup.strength_score:.0f}"
            )

    print(
        "\nLimits: two years, current-symbol survivorship, raw DSE OHLC, no intraday fill model, "
        "and multiple configurations examined on train. Validation is necessary, not conclusive."
    )


if __name__ == "__main__":
    asyncio.run(_run())
