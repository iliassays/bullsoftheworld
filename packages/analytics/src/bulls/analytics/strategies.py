"""Deterministic buy/sell rules for the five agent model portfolios. Pure — no I/O, no clock.

Grounded in our own factor study (docs/research/dse-trading-research.md, 2024-06 → 2026-06):
contrarian was the strongest family (oversold-RSI IC +0.094 @ 60d, 82% hit rate), quality mildly
positive, value flat, and momentum NEGATIVE (IC -0.077 @ 60d) — so there is deliberately no
trend-following strategy here, and the flagship "rebound" strategy is the study's Quality
Reversal scheme (washout + profitable + cheap + up-tick trigger; backtested +73.6% vs +7.8%
buy-and-hold, single recovering-market regime — treat as evidence="framework", not a promise).

Simulation honesty: entries refuse a stock ticking near its upper circuit lock and exits refuse
one near its lower lock — a fill at a limit-locked price has no real counterparty, and a paper
portfolio that "trades" there is faking data. Missing analytics fields always mean "no entry"
(omit-over-mislead), but the hard stop-loss still works on price alone.

These portfolios are the platform's own paper accounts, reviewed from the admin cockpit.
Descriptive reasons accompany every decision; nothing here is investor-facing advice.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

# --- inputs ----------------------------------------------------------------------------------

# Universe gates — same posture as the trending engine's public gates (docs/specs/trending-engine.md):
# median-ish daily turnover >= ৳50 lakh, market cap >= ৳50 crore, never Z-category.
_MIN_TURNOVER = 5_000_000.0  # ৳, avg_volume_20 x last_close
_MIN_MCAP_MN = 500.0  # ৳50 crore in millions
# A stock moving ±8%+ on the day is at/near its DSE circuit lock (±10% band for most prices):
# no realistic counterparty on the locked side.
_CIRCUIT_GUARD_PCT = 8.0


@dataclass(frozen=True)
class Snapshot:
    """Everything the rules may look at for one stock: the live quote (15-min poll) plus the
    EOD TickerAnalytics row. None = the fact is unknown today; rules must treat unknown as
    disqualifying, never assume."""

    code: str
    sector: str | None
    category: str | None
    ltp: float
    change_pct: float | None
    quote_as_of: dt.datetime
    last_close: float | None
    rsi_14: float | None
    pct_from_52w_high: float | None  # negative below the high
    pct_from_52w_low: float | None  # positive above the low
    pe_ratio: float | None  # None when EPS <= 0 (loss-maker)
    pb_ratio: float | None
    pe_vs_sector: float | None  # < 1 = cheaper than sector median
    roe: float | None
    eps_growth_yoy: float | None
    dividend_yield: float | None
    volatility: float | None
    cmf_20: float | None
    obv_slope: float | None
    institute_delta: float | None
    foreign_delta: float | None
    rel_volume_5d: float | None
    relative_volume: float | None
    avg_volume_20: float | None
    market_cap_mn: float | None


def universe_ok(s: Snapshot) -> bool:
    """Hard gates every strategy shares. Unknown liquidity/size = not tradable."""
    if s.category == "Z":  # T+3, cash-only, weakest disclosure — out entirely
        return False
    if s.avg_volume_20 is None or s.last_close is None or s.market_cap_mn is None:
        return False
    if s.avg_volume_20 * s.last_close < _MIN_TURNOVER:
        return False
    return not s.market_cap_mn < _MIN_MCAP_MN


def _near_upper_lock(s: Snapshot) -> bool:
    return s.change_pct is not None and s.change_pct >= _CIRCUIT_GUARD_PCT


def _near_lower_lock(s: Snapshot) -> bool:
    return s.change_pct is not None and s.change_pct <= -_CIRCUIT_GUARD_PCT


# --- strategy specs ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StrategySpec:
    key: str
    display_name: str
    handle: str  # the bot user's handle — suffix "Portfolio" by design
    description: str
    entry: Callable[[Snapshot], str | None]  # reason if the setup qualifies right now
    rank: Callable[[Snapshot], float]  # higher = buy first when cash is short
    exit_extra: Callable[[Snapshot], str | None]  # strategy exit beyond stop/target
    stop_loss_pct: float
    take_profit_pct: float | None
    max_positions: int = 6
    position_pct: float = 0.15  # of initial capital per new position


def _rebound_entry(s: Snapshot) -> str | None:
    if (
        s.pct_from_52w_high is not None
        and s.pct_from_52w_high <= -40
        and s.pct_from_52w_low is not None
        and s.pct_from_52w_low <= 15
        and s.pe_ratio is not None  # profitable …
        and s.pe_ratio <= 25  # … and not expensive
        and s.rsi_14 is not None
        and s.rsi_14 <= 40
        and s.change_pct is not None
        and s.change_pct >= 1.0  # the up-tick trigger: washouts are bought on a turn, not a knife
        and (s.relative_volume or 0) >= 1.2
    ):
        return (
            f"Washout reversal setup: {s.pct_from_52w_high:.0f}% off 52w high, "
            f"{s.pct_from_52w_low:.0f}% above the low, P/E {s.pe_ratio:.1f}, RSI {s.rsi_14:.0f}, "
            f"turning +{s.change_pct:.1f}% on {s.relative_volume:.1f}x volume"
        )
    return None


def _rebound_exit(s: Snapshot) -> str | None:
    if s.rsi_14 is not None and s.rsi_14 >= 65:
        return f"RSI recovered to {s.rsi_14:.0f} — the oversold thesis has played out"
    return None


def _value_entry(s: Snapshot) -> str | None:
    if (
        s.pe_vs_sector is not None
        and s.pe_vs_sector <= 0.8
        and s.pe_ratio is not None
        and s.pe_ratio <= 15
        and s.pb_ratio is not None
        and s.pb_ratio <= 1.5
        and s.roe is not None
        and s.roe >= 8  # value-trap gate: cheap AND still earning its keep
    ):
        return (
            f"Cheap vs own sector: P/E {s.pe_ratio:.1f} ({s.pe_vs_sector:.2f}x sector median), "
            f"P/B {s.pb_ratio:.2f}, ROE {s.roe:.0f}%"
        )
    return None


def _value_exit(s: Snapshot) -> str | None:
    if s.pe_vs_sector is not None and s.pe_vs_sector >= 1.05:
        return f"No longer cheap: {s.pe_vs_sector:.2f}x sector median P/E"
    return None


def _quality_entry(s: Snapshot) -> str | None:
    if (
        s.roe is not None
        and s.roe >= 15
        and s.eps_growth_yoy is not None
        and s.eps_growth_yoy >= 0
        and s.pe_ratio is not None
        and s.pe_ratio <= 25
    ):
        return (
            f"Quality compounder: ROE {s.roe:.0f}%, EPS growth {s.eps_growth_yoy:+.0f}% YoY, "
            f"P/E {s.pe_ratio:.1f}"
        )
    return None


def _quality_exit(s: Snapshot) -> str | None:
    if s.roe is not None and s.roe < 10:
        return f"Quality deteriorated: ROE down to {s.roe:.0f}%"
    return None


def _dividend_entry(s: Snapshot) -> str | None:
    if (
        s.dividend_yield is not None
        and s.dividend_yield >= 4
        and s.volatility is not None
        and s.volatility <= 40
        and s.pe_ratio is not None  # profitable — a yield without earnings won't repeat
    ):
        return (
            f"Income setup: {s.dividend_yield:.1f}% dividend yield, "
            f"{s.volatility:.0f}% volatility, P/E {s.pe_ratio:.1f}"
        )
    return None


def _dividend_exit(s: Snapshot) -> str | None:
    if s.dividend_yield is not None and s.dividend_yield < 2.5:
        return f"Yield compressed to {s.dividend_yield:.1f}% — income case gone"
    return None


def _accumulation_entry(s: Snapshot) -> str | None:
    inst = s.institute_delta or 0
    forn = s.foreign_delta or 0
    if (
        s.cmf_20 is not None
        and s.cmf_20 >= 0.10
        and s.obv_slope is not None
        and s.obv_slope > 0
        and (inst > 0 or forn > 0)
        and s.rel_volume_5d is not None
        and s.rel_volume_5d >= 1.1
    ):
        who = "institutions" if inst >= forn else "foreign investors"
        delta = max(inst, forn)
        return (
            f"Quiet accumulation: CMF {s.cmf_20:.2f}, OBV rising, {who} +{delta:.1f}pp last "
            f"month, 5d volume {s.rel_volume_5d:.1f}x normal"
        )
    return None


def _accumulation_exit(s: Snapshot) -> str | None:
    if s.cmf_20 is not None and s.cmf_20 <= -0.05:
        return f"Money flow turned to distribution (CMF {s.cmf_20:.2f})"
    return None


STRATEGIES: dict[str, StrategySpec] = {
    spec.key: spec
    for spec in (
        StrategySpec(
            key="rebound",
            display_name="Rebound Portfolio",
            handle="ReboundPortfolio",
            description=(
                "Contrarian quality-reversal: deeply washed-out but profitable stocks, bought on "
                "the first confirmed up-tick. The strongest family in our DSE factor study."
            ),
            entry=_rebound_entry,
            rank=lambda s: -(s.rsi_14 or 100),  # the more oversold, the better
            exit_extra=_rebound_exit,
            stop_loss_pct=-10.0,
            take_profit_pct=20.0,
        ),
        StrategySpec(
            key="value",
            display_name="Value Portfolio",
            handle="ValuePortfolio",
            description="Cheap versus own sector on earnings and book, with a value-trap gate.",
            entry=_value_entry,
            rank=lambda s: -(s.pe_vs_sector or 9.9),
            exit_extra=_value_exit,
            stop_loss_pct=-12.0,
            take_profit_pct=None,
        ),
        StrategySpec(
            key="quality",
            display_name="Quality Portfolio",
            handle="QualityPortfolio",
            description="High return-on-equity compounders at a sane price, held while quality holds.",
            entry=_quality_entry,
            rank=lambda s: s.roe or 0,
            exit_extra=_quality_exit,
            stop_loss_pct=-12.0,
            take_profit_pct=None,
        ),
        StrategySpec(
            key="dividend",
            display_name="Dividend Portfolio",
            handle="DividendPortfolio",
            description="Steady payers: real yield, calm price, profitable underneath.",
            entry=_dividend_entry,
            rank=lambda s: s.dividend_yield or 0,
            exit_extra=_dividend_exit,
            stop_loss_pct=-12.0,
            take_profit_pct=None,
        ),
        StrategySpec(
            key="accumulation",
            display_name="Accumulation Portfolio",
            handle="AccumulationPortfolio",
            description=(
                "Follows the platform's ownership data: money-flow positive names institutions or "
                "foreign investors are actually adding to."
            ),
            entry=_accumulation_entry,
            rank=lambda s: (s.cmf_20 or 0) + max(s.institute_delta or 0, s.foreign_delta or 0),
            exit_extra=_accumulation_exit,
            stop_loss_pct=-10.0,
            take_profit_pct=15.0,
        ),
    )
}


# --- decision API (what the engine calls) -----------------------------------------------------


def entry_reason(strategy: str, s: Snapshot) -> str | None:
    """Why this stock qualifies for a NEW position right now, or None. Applies universe gates and
    the upper-circuit guard before the strategy's own rules."""
    if not universe_ok(s) or _near_upper_lock(s):
        return None
    return STRATEGIES[strategy].entry(s)


def exit_reason(strategy: str, s: Snapshot, *, avg_cost: float) -> str | None:
    """Why an EXISTING position should be closed right now, or None. The hard stop and take-profit
    work on price alone (they must survive missing analytics); the lower-circuit guard blocks all
    exits — a limit-locked stock has no bid to sell into, pretending otherwise is a fake fill."""
    if _near_lower_lock(s):
        return None
    spec = STRATEGIES[strategy]
    if avg_cost > 0:
        pnl_pct = (s.ltp - avg_cost) / avg_cost * 100
        if pnl_pct <= spec.stop_loss_pct:
            return f"Stop-loss: {pnl_pct:.1f}% vs avg cost {avg_cost:.2f}"
        if spec.take_profit_pct is not None and pnl_pct >= spec.take_profit_pct:
            return f"Target reached: {pnl_pct:+.1f}% vs avg cost {avg_cost:.2f}"
    return spec.exit_extra(s)


def rank_entries(
    strategy: str, snapshots: Iterable[Snapshot], *, held: set[str]
) -> Sequence[tuple[Snapshot, str]]:
    """All qualifying new entries, best-ranked first, excluding codes already held."""
    spec = STRATEGIES[strategy]
    out: list[tuple[Snapshot, str]] = []
    for s in snapshots:
        if s.code in held:
            continue
        reason = entry_reason(strategy, s)
        if reason is not None:
            out.append((s, reason))
    out.sort(key=lambda pair: spec.rank(pair[0]), reverse=True)
    return out
