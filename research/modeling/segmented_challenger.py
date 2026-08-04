"""Causal universe sleeves and portfolio construction for the Atlas rank challenger.

This module is deliberately independent of database and order code.  It consumes observations
already built at a completed session close, applies only fields known at that close, and returns
diagnostic portfolio metrics.  Historical capitalization is intentionally absent: the production
store cannot reconstruct point-in-time market cap before July 2026, so using today's cap tier in a
historical test would leak future information.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import polars as pl


@dataclass(frozen=True, slots=True)
class PortfolioConstructionSpec:
    """Frozen long-only construction contract for one independently funded sleeve."""

    book_notional: float
    max_positions: int = 10
    minimum_positions: int = 8
    max_position_weight: float = 0.15
    max_adv_participation: float = 0.01
    minimum_predicted_net_excess: float = 0.0


@dataclass(frozen=True, slots=True)
class LiquiditySleeveSpec:
    """A point-in-time tradability sleeve; names do not imply unavailable capitalization."""

    key: str
    label: str
    minimum_price: float
    minimum_adv: float
    maximum_adv: float | None
    minimum_cross_section: int
    allowed_trend_regimes: tuple[str, ...]
    allowed_volatility_regimes: tuple[str, ...]
    construction: PortfolioConstructionSpec

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_LIQUIDITY_SLEEVES = (
    LiquiditySleeveSpec(
        key="deep_liquidity",
        label="Deep liquidity",
        minimum_price=5.0,
        minimum_adv=50_000_000.0,
        maximum_adv=None,
        minimum_cross_section=50,
        allowed_trend_regimes=("risk_on", "transition"),
        allowed_volatility_regimes=("normal",),
        construction=PortfolioConstructionSpec(book_notional=5_000_000.0),
    ),
    LiquiditySleeveSpec(
        key="institutional_liquidity",
        label="Institutional liquidity",
        minimum_price=3.0,
        minimum_adv=10_000_000.0,
        maximum_adv=50_000_000.0,
        minimum_cross_section=50,
        allowed_trend_regimes=("risk_on",),
        allowed_volatility_regimes=("normal",),
        construction=PortfolioConstructionSpec(book_notional=1_000_000.0),
    ),
    LiquiditySleeveSpec(
        key="size_sensitive",
        label="Size-sensitive liquidity",
        minimum_price=2.0,
        minimum_adv=5_000_000.0,
        maximum_adv=10_000_000.0,
        minimum_cross_section=30,
        allowed_trend_regimes=("risk_on",),
        allowed_volatility_regimes=("normal",),
        construction=PortfolioConstructionSpec(book_notional=250_000.0),
    ),
)


def filter_liquidity_sleeve(
    frame: pl.DataFrame,
    sleeve: LiquiditySleeveSpec,
) -> pl.DataFrame:
    """Apply the frozen price, liquidity, market-regime, and breadth requirements."""

    required = {
        "date",
        "close",
        "adv_20",
        "benchmark_trend_regime",
        "benchmark_volatility_regime",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing sleeve columns: {sorted(missing)}")
    condition = (
        (pl.col("close") >= sleeve.minimum_price)
        & (pl.col("adv_20") >= sleeve.minimum_adv)
        & pl.col("benchmark_trend_regime").is_in(sleeve.allowed_trend_regimes)
        & pl.col("benchmark_volatility_regime").is_in(
            sleeve.allowed_volatility_regimes
        )
    )
    if sleeve.maximum_adv is not None:
        condition &= pl.col("adv_20") < sleeve.maximum_adv
    eligible = frame.filter(condition)
    return eligible.filter(pl.len().over("date") >= sleeve.minimum_cross_section)


def bounded_inverse_volatility_weights(
    volatility: np.ndarray,
    capacity: np.ndarray,
) -> np.ndarray | None:
    """Allocate one unit of capital by inverse volatility subject to hard weight caps."""

    if volatility.ndim != 1 or capacity.ndim != 1 or volatility.size != capacity.size:
        raise ValueError("volatility and capacity must be equal one-dimensional arrays")
    if volatility.size == 0 or np.any(~np.isfinite(volatility)):
        return None
    if np.any(~np.isfinite(capacity)) or np.any(capacity <= 0) or capacity.sum() < 1.0:
        return None

    inverse = 1.0 / np.clip(volatility, 0.005, None)
    weights = np.zeros(volatility.size, dtype=float)
    active = np.ones(volatility.size, dtype=bool)
    remaining = 1.0
    for _ in range(volatility.size + 1):
        active_total = float(inverse[active].sum())
        if remaining <= 1e-10:
            break
        if not active.any() or active_total <= 0:
            return None
        proposal = np.zeros_like(weights)
        proposal[active] = remaining * inverse[active] / active_total
        breached = active & (proposal > capacity + 1e-12)
        if not breached.any():
            weights += proposal
            remaining = 0.0
            break
        weights[breached] = capacity[breached]
        remaining = 1.0 - float(weights.sum())
        active[breached] = False
    if remaining > 1e-8 or not math.isclose(float(weights.sum()), 1.0, abs_tol=1e-8):
        return None
    return weights


def _drawdown(returns: np.ndarray) -> float | None:
    if returns.size == 0:
        return None
    equity = np.cumprod(1.0 + returns)
    peaks = np.maximum.accumulate(equity)
    return float(np.min(equity / peaks - 1.0))


def evaluate_constructed_book(
    frame: pl.DataFrame,
    *,
    score_column: str,
    horizon: int,
    construction: PortfolioConstructionSpec,
) -> dict[str, Any]:
    """Evaluate a capacity-capped inverse-volatility top book with explicit abstention."""

    if horizon < 1:
        raise ValueError("horizon must be positive")
    if construction.minimum_positions < 1:
        raise ValueError("minimum_positions must be positive")
    if construction.minimum_positions > construction.max_positions:
        raise ValueError("minimum_positions cannot exceed max_positions")
    required = {
        "date",
        "code",
        "adv_20",
        "volatility_20",
        "net_excess",
        "stressed_net_excess",
        "gross_excess",
        score_column,
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing construction columns: {sorted(missing)}")

    clean = frame.drop_nulls(list(required)).filter(
        pl.all_horizontal(*(pl.col(name).is_finite() for name in required if name not in {"date", "code"}))
    )
    if clean.is_empty():
        return {"dates": 0, "invested_dates": 0, "trades": 0}

    rows: list[dict[str, float | int]] = []
    selected_symbols: set[str] = set()
    abstentions: Counter[str] = Counter()
    effective_names: list[float] = []
    selected_adv: list[float] = []
    considered_dates = 0

    for day in clean.sort(["date", score_column], descending=[False, True]).partition_by(
        "date", maintain_order=True
    ):
        considered_dates += 1
        candidates = (
            day.filter(pl.col(score_column) > construction.minimum_predicted_net_excess)
            .head(construction.max_positions)
        )
        if candidates.height < construction.minimum_positions:
            abstentions["insufficient_positive_scores"] += 1
            continue
        volatility = candidates["volatility_20"].to_numpy()
        adv = candidates["adv_20"].to_numpy()
        capacity = np.minimum(
            construction.max_position_weight,
            adv * construction.max_adv_participation / construction.book_notional,
        )
        weights = bounded_inverse_volatility_weights(volatility, capacity)
        if weights is None:
            abstentions["insufficient_capacity"] += 1
            continue
        net = float(weights @ candidates["net_excess"].to_numpy())
        stressed = float(weights @ candidates["stressed_net_excess"].to_numpy())
        gross = float(weights @ candidates["gross_excess"].to_numpy())
        rows.append({"net": net, "stressed": stressed, "gross": gross, "trades": candidates.height})
        selected_symbols.update(str(code) for code in candidates["code"].to_list())
        effective_names.append(float(1.0 / np.sum(weights**2)))
        selected_adv.extend(float(value) for value in adv)

    if not rows:
        return {
            "dates": considered_dates,
            "invested_dates": 0,
            "trades": 0,
            "abstentions": dict(abstentions),
        }
    returns = np.asarray([float(row["net"]) for row in rows])
    stressed = np.asarray([float(row["stressed"]) for row in rows])
    periods_per_year = 252.0 / horizon
    standard_deviation = float(np.std(returns, ddof=1)) if returns.size > 1 else 0.0
    sharpe = (
        float(np.mean(returns) / standard_deviation * math.sqrt(periods_per_year))
        if standard_deviation > 0
        else None
    )
    sharpe_standard_error: float | None = None
    sharpe_lower_95: float | None = None
    if sharpe is not None and returns.size > 1:
        periodic = sharpe / math.sqrt(periods_per_year)
        sharpe_standard_error = float(
            math.sqrt((1.0 + 0.5 * periodic**2) / returns.size)
            * math.sqrt(periods_per_year)
        )
        sharpe_lower_95 = float(sharpe - 1.96 * sharpe_standard_error)

    return {
        "dates": considered_dates,
        "invested_dates": len(rows),
        "trades": sum(int(row["trades"]) for row in rows),
        "symbols": len(selected_symbols),
        "years": float(len(rows) / periods_per_year),
        "mean_net_pct": float(np.mean(returns) * 100.0),
        "mean_stressed_pct": float(np.mean(stressed) * 100.0),
        "annualized_net_pct": float(np.mean(returns) * periods_per_year * 100.0),
        "hit_rate_pct": float(np.mean(returns > 0) * 100.0),
        "sharpe": sharpe,
        "sharpe_standard_error": sharpe_standard_error,
        "sharpe_lower_95": sharpe_lower_95,
        "maximum_drawdown_pct": (
            _drawdown(returns) * 100.0 if _drawdown(returns) is not None else None
        ),
        "mean_effective_positions": float(np.mean(effective_names)),
        "median_selected_adv": float(np.median(selected_adv)),
        "abstentions": dict(abstentions),
    }


__all__ = [
    "DEFAULT_LIQUIDITY_SLEEVES",
    "LiquiditySleeveSpec",
    "PortfolioConstructionSpec",
    "bounded_inverse_volatility_weights",
    "evaluate_constructed_book",
    "filter_liquidity_sleeve",
]
