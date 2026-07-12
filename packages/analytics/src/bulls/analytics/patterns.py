"""Classic chart-pattern detection (Finviz-style): named geometric shapes from confirmed swing
pivots on daily bars.

Pure computation, no I/O — same style as `engine.py`. Builds on `swing_high_indices`/
`swing_low_indices` (indicators.py): fits a trendline through recent swing highs (resistance) and
swing lows (support), then classifies the resulting shape by slope and convergence, or checks two
comparable extremes for a double top/bottom.

This is textbook technical analysis, NOT proven to have predictive edge on DSE. Our own factor
study (docs/research/dse-trading-research.md) found the conceptually-related trend-following
factor, momentum, actually HURT returns here (IC -0.077 @ 60d). So callers must label this
evidence="framework" (classic method, unproven locally) — never "backtested" — until a dedicated
study says otherwise.

Scope: channel_horizontal, channel_up, channel_down, ascending_triangle, descending_triangle,
double_top, double_bottom, and a strict high-volume flat base. The flat base has a dedicated
walk-forward study: it improved selectivity over a generic volume breakout but did not show stable
standalone return edge across regimes, so it remains framework evidence and a watchlist tool.
Wedges and head-and-shoulders are deliberately not detected; both need a manual accuracy pass.

The exact thresholds below (MIN_STRENGTH, the 3%/5% tolerances, the touch/duration weights in the
strength score) are an initial calibration, not tuned against real DSE data yet — see the
spot-check step in the implementation plan before trusting this at scale.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import BaseModel

from bulls.analytics.flat_base import DEFAULT_FLAT_BASE_CONFIG, FlatBaseSetup, detect_flat_base_at
from bulls.analytics.indicators import atr, linreg, swing_high_indices, swing_low_indices

LOOKBACK = 150  # trading days (~7 months) — enough for these shapes to form without going stale
MIN_STRENGTH = 62.0  # 0-100 gate: below this, a "match" is closer to noise than a real shape
_MIN_PIVOT_GAP = 10  # bars between two pivots to count as genuinely distinct (double top/bottom)


class BarLike(Protocol):
    date: dt.date
    high: float
    low: float
    close: float


PatternType = Literal[
    "double_top",
    "double_bottom",
    "ascending_triangle",
    "descending_triangle",
    "channel_up",
    "channel_down",
    "channel_horizontal",
    "high_volume_flat_base",
]
PatternStatus = Literal[
    "forming", "confirmed_breakout_up", "confirmed_breakout_down", "invalidated"
]


class PricePoint(BaseModel):
    date: dt.date
    price: float


class PatternPoint(PricePoint):
    kind: Literal["high", "low"]


class LineSeg(BaseModel):
    start: PricePoint
    end: PricePoint


class PatternMatch(BaseModel):
    """One detected shape. Descriptive only — never a buy/sell signal."""

    pattern_type: PatternType
    status: PatternStatus
    start_date: dt.date
    end_date: dt.date
    breakout_date: dt.date | None = None
    pivots: list[PatternPoint] = []
    resistance_line: LineSeg | None = None
    support_line: LineSeg | None = None
    key_levels: list[float] = []  # e.g. the neckline for a double top/bottom
    strength_score: float
    touches_resistance: int = 0
    touches_support: int = 0
    metrics: dict[str, float] = {}


_FLAT_BASE_BREAKOUT_RETENTION = 5


def _flat_base_match(rows: Sequence[BarLike]) -> PatternMatch | None:
    """Adapt the volume-aware setup into the shared chart-pattern payload."""
    if not rows or any(not hasattr(bar, "volume") for bar in rows):
        return None

    setup: FlatBaseSetup | None = detect_flat_base_at(
        rows, len(rows) - 1, config=DEFAULT_FLAT_BASE_CONFIG
    )
    sessions_since_breakout = 0
    if setup is None:
        for age in range(1, min(_FLAT_BASE_BREAKOUT_RETENTION, len(rows) - 1) + 1):
            candidate = detect_flat_base_at(
                rows,
                len(rows) - 1 - age,
                config=DEFAULT_FLAT_BASE_CONFIG,
            )
            if candidate is None or candidate.status != "confirmed_breakout_up":
                continue
            if rows[-1].close < candidate.resistance:
                continue
            setup = candidate
            sessions_since_breakout = age
            break
    if setup is None:
        return None

    current_date = rows[-1].date
    current_close = rows[-1].close
    confirmed = setup.status == "confirmed_breakout_up"
    strength = max(0.0, setup.strength_score - 2 * sessions_since_breakout)
    return PatternMatch(
        pattern_type="high_volume_flat_base",
        status=setup.status,
        start_date=setup.start_date,
        end_date=current_date,
        breakout_date=setup.as_of_date if confirmed else None,
        resistance_line=LineSeg(
            start=PricePoint(date=setup.start_date, price=setup.resistance),
            end=PricePoint(date=current_date, price=setup.resistance),
        ),
        support_line=LineSeg(
            start=PricePoint(date=setup.start_date, price=setup.support),
            end=PricePoint(date=current_date, price=setup.support),
        ),
        key_levels=[setup.resistance, setup.support],
        strength_score=round(strength, 1),
        touches_resistance=setup.resistance_touches,
        metrics={
            "base_depth_pct": round(100 * setup.depth, 2),
            "volume_ratio": round(setup.volume_ratio, 2),
            "dry_up_ratio": round(setup.dry_up_ratio, 2),
            "average_turnover": setup.average_turnover,
            "distance_to_breakout_pct": round(
                100 * max(setup.resistance / current_close - 1, 0), 2
            ),
            "sessions_since_breakout": float(sessions_since_breakout),
        },
    )


class _Fit:
    """A trendline fit through a handful of same-type pivots, in window-relative bar-index space."""

    __slots__ = ("first_idx", "intercept", "last_idx", "residual", "se_slope", "slope", "touches")

    def __init__(
        self,
        slope: float,
        intercept: float,
        touches: int,
        residual: float,
        se_slope: float,
        first_idx: int,
        last_idx: int,
    ) -> None:
        self.slope = slope
        self.intercept = intercept
        self.touches = touches
        self.residual = residual
        self.se_slope = se_slope
        self.first_idx = first_idx
        self.last_idx = last_idx

    def at(self, x: float) -> float:
        return self.slope * x + self.intercept


_MAX_FIT_TOUCHES = 6  # cap on pivots used per line — must match the touch_bonus ceiling below
_MIN_SLOPE_T_STAT = 3.0  # how many standard errors the slope must clear to call it a real trend


def _fit_pivots(idxs: Sequence[int], values: Sequence[float]) -> _Fit | None:
    """Fit a line through the most recent pivots of one type (up to the last 6 — enough headroom
    for the strength score to reward extra confirming touches without old, no-longer-relevant
    pivots pulling on the line).

    Requires >= 3 points, not 2: a 2-point line ALWAYS has zero residual (any two points are
    perfectly collinear), which would falsely max out the fit-quality score for a completely
    arbitrary pair of pivots — confirmed live: pure random-walk noise was producing "confident"
    channel/triangle matches until this was tightened (2026-07-05 spot-check before ship)."""
    if len(idxs) < 3:
        return None
    use = list(idxs[-_MAX_FIT_TOUCHES:])
    xs = [float(i) for i in use]
    ys = [values[i] for i in use]
    fit = linreg(xs, ys)
    if fit is None:
        return None
    slope, intercept = fit
    n = len(xs)
    resids = [(slope * x + intercept) - y for x, y in zip(xs, ys, strict=True)]
    residual = statistics.fmean(abs(r) for r in resids)
    xbar = statistics.fmean(xs)
    sxx = sum((x - xbar) ** 2 for x in xs)
    # Standard error of the slope (simple OLS formula) — used to test whether the slope is
    # distinguishable from zero given how scattered the points are, rather than just eyeballing
    # the raw price move against ATR (see _slope_class for why the raw-move version wasn't enough).
    if n > 2 and sxx > 0:
        sse = sum(r * r for r in resids)
        se_slope = math.sqrt((sse / (n - 2)) / sxx)
    else:
        se_slope = float("inf")
    return _Fit(slope, intercept, n, residual, se_slope, use[0], use[-1])


def _slope_class(fit: _Fit) -> str:
    """ "flat" / "rising" / "falling" — a slope only counts as a real trend if it clears
    _MIN_SLOPE_T_STAT standard errors of its own fit, i.e. it's not just noise scatter around an
    essentially flat line. An earlier version compared the implied price move to ATR instead; that
    let short bursts of ordinary wobble in truly flat/mean-reverting series get read as "rising" or
    "falling" (confirmed live: 60%+ false-positive rate against synthetic mean-reverting noise,
    2026-07-05 spot-check before ship) — the t-stat version is scale-free and accounts for how
    tightly the points actually sit on the line, not just the raw distance moved."""
    if fit.se_slope == 0:
        return "rising" if fit.slope > 0 else ("falling" if fit.slope < 0 else "flat")
    if abs(fit.slope) / fit.se_slope < _MIN_SLOPE_T_STAT:
        return "flat"
    return "rising" if fit.slope > 0 else "falling"


def _detect_triangle_channel(
    sh_idx: Sequence[int],
    sl_idx: Sequence[int],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    dates: Sequence[dt.date],
    atr14: float | None,
    n: int,
) -> PatternMatch | None:
    res = _fit_pivots(sh_idx, highs)
    sup = _fit_pivots(sl_idx, lows)
    if res is None or sup is None:
        return None

    x_start = float(min(res.first_idx, sup.first_idx))
    x_end = float(n - 1)
    gap_start = res.at(x_start) - sup.at(x_start)
    gap_end = res.at(x_end) - sup.at(x_end)
    if gap_start <= 0 or gap_end <= 0:
        return None  # lines already crossed — not a coherent channel/triangle
    if gap_end > 1.4 * gap_start:
        return None  # diverging — no pattern name in this scope

    converging = gap_end < 0.6 * gap_start
    res_class = _slope_class(res)
    sup_class = _slope_class(sup)

    pattern_type: PatternType | None = None
    if res_class == "flat" and sup_class == "rising":
        pattern_type = "ascending_triangle"
    elif res_class == "falling" and sup_class == "flat":
        pattern_type = "descending_triangle"
    elif res_class == "rising" and sup_class == "rising" and not converging:
        pattern_type = "channel_up"
    elif res_class == "falling" and sup_class == "falling" and not converging:
        pattern_type = "channel_down"
    elif res_class == "flat" and sup_class == "flat":
        pattern_type = "channel_horizontal"
    if pattern_type is None:
        return None  # converging rising/falling (wedges) and mixed shapes: out of v1 scope

    # A "flat" classification means the fitted slope isn't statistically distinguishable from
    # zero (see _slope_class) — but the raw fit still HAS a small nonzero slope, and extrapolating
    # that slope all the way out to the latest bar can imply a much bigger move than the fit
    # actually supports, both for the breakout comparison and for drawing the line. So a flat
    # line's effective value anywhere is just its own average over the fitted pivots, not
    # slope*x+intercept (confirmed by spot-check before ship: a "channel_horizontal" was
    # rendering as two steep diagonal lines because of this, 2026-07-05).
    def _effective(fit: _Fit, cls: str, x: float) -> float:
        if cls == "flat":
            return (fit.at(fit.first_idx) + fit.at(fit.last_idx)) / 2
        return fit.at(x)

    last_close = closes[-1]
    buffer = 0.5 * atr14 if atr14 else 0.0
    upper_now = _effective(res, res_class, x_end)
    lower_now = _effective(sup, sup_class, x_end)
    breakout_date: dt.date | None = None
    if last_close > upper_now + buffer:
        status: PatternStatus = "confirmed_breakout_up"
        breakout_date = dates[-1]
    elif last_close < lower_now - buffer:
        status = "confirmed_breakout_down"
        breakout_date = dates[-1]
    else:
        status = "forming"

    # A confirmed pivot AFTER the ones used to fit a line already sits on the wrong side of that
    # line by more than the breakout buffer: the shape broke before any real breakout close, so
    # it's stale rather than "still forming".
    if any(i > res.last_idx and highs[i] > _effective(res, res_class, i) + buffer for i in sh_idx):
        status = "invalidated"
    if any(i > sup.last_idx and lows[i] < _effective(sup, sup_class, i) - buffer for i in sl_idx):
        status = "invalidated"

    start_idx = int(x_start)
    span_bars = x_end - x_start
    duration_quality = min(1.0, span_bars / 40)  # patterns under ~8 weeks are thin evidence
    denom = atr14 if atr14 else max(res.residual, sup.residual, 1e-6)
    fit_quality = max(0.0, 1 - ((res.residual + sup.residual) / 2) / denom) if denom else 0.5
    # Extra touches carry the most weight deliberately: a trendline is trivially "well-fit" by
    # any 3 arbitrary points, but each ADDITIONAL confirmed touch (up to _MAX_FIT_TOUCHES) is
    # genuinely hard for a merely noisy series to keep landing on the same line by chance — this
    # is what should separate a real, respected boundary from an incidental 3-point fit through
    # drift. The bare minimum of 3 touches on both lines, even with a flawless fit, tops out at
    # 50 (20 base + 15 fit + 15 duration) — deliberately below MIN_STRENGTH, so a pattern needs at
    # least one line with a 4th confirming touch to ever surface.
    extra = _MAX_FIT_TOUCHES - 3
    touch_bonus = min(res.touches - 3, extra) * (25 / extra) + min(sup.touches - 3, extra) * (
        25 / extra
    )
    strength = 20 + 15 * fit_quality + 15 * duration_quality + touch_bonus
    if status.startswith("confirmed_breakout"):
        strength += 10  # a resolved pattern is more interesting than one still forming

    pivots = [PatternPoint(date=dates[i], price=highs[i], kind="high") for i in sh_idx[-4:]] + [
        PatternPoint(date=dates[i], price=lows[i], kind="low") for i in sl_idx[-4:]
    ]

    return PatternMatch(
        pattern_type=pattern_type,
        status=status,
        start_date=dates[start_idx],
        end_date=breakout_date or dates[-1],
        breakout_date=breakout_date,
        pivots=pivots,
        resistance_line=LineSeg(
            start=PricePoint(
                date=dates[res.first_idx], price=round(_effective(res, res_class, res.first_idx), 2)
            ),
            end=PricePoint(date=dates[-1], price=round(upper_now, 2)),
        ),
        support_line=LineSeg(
            start=PricePoint(
                date=dates[sup.first_idx], price=round(_effective(sup, sup_class, sup.first_idx), 2)
            ),
            end=PricePoint(date=dates[-1], price=round(lower_now, 2)),
        ),
        strength_score=round(min(max(strength, 0.0), 100.0), 1),
        touches_resistance=res.touches,
        touches_support=sup.touches,
    )


def _detect_double(
    idxs: Sequence[int],
    extreme_vals: Sequence[float],
    between_vals: Sequence[float],
    closes: Sequence[float],
    dates: Sequence[dt.date],
    atr14: float | None,
    *,
    top: bool,
) -> PatternMatch | None:
    """Shared logic for double top (top=True, over swing highs) and double bottom (top=False, over
    swing lows) — the two are exact mirrors of each other.

    Tolerances are deliberately strict: a first pass with a 3% comparable-peaks / 5% retracement
    floor was firing on 17 of 20 pure random-walk test series (confirmed by spot-check before
    ship, 2026-07-05) — coincidental "two similar local highs with a dip between them" is common
    in any noisy series. The fix is two-fold: tighter tolerances, AND requiring the two pivots to
    actually be the standout extremes of the whole window, not just locally notable."""
    if len(idxs) < 2:
        return None
    i1, i2 = idxs[-2], idxs[-1]
    if i2 - i1 < _MIN_PIVOT_GAP:
        return None
    v1, v2 = extreme_vals[i1], extreme_vals[i2]
    avg = (v1 + v2) / 2
    if avg <= 0:
        return None
    atr_pct = (atr14 / avg) if atr14 else 0.0
    diff_tolerance = max(0.02, 0.4 * atr_pct)
    diff_pct = abs(v1 - v2) / avg
    if diff_pct > diff_tolerance:
        return None  # the two extremes aren't comparable enough to read as "the same level twice"

    # Both pivots must actually be the standout extreme of the whole window (within 3% of the
    # window's own high/low), not merely a locally-confirmed swing partway up/down a trend.
    window_extreme = max(extreme_vals) if top else min(extreme_vals)
    worse_of_the_two = min(v1, v2) if top else max(v1, v2)
    if window_extreme <= 0:
        return None
    if abs(window_extreme - worse_of_the_two) / abs(window_extreme) > 0.03:
        return None

    between = between_vals[i1 : i2 + 1]
    mid = min(between) if top else max(between)
    ref = min(v1, v2) if top else max(v1, v2)
    if ref <= 0:
        return None
    retrace_tolerance = max(0.08, 2.0 * atr_pct)
    retrace_pct = abs(ref - mid) / ref
    if retrace_pct < retrace_tolerance:
        return None  # no meaningful pullback between the two peaks/troughs — just noise on one

    last_close = closes[-1]
    buffer = 0.5 * atr14 if atr14 else 0.0
    breakout_date: dt.date | None = None
    if top:
        status: PatternStatus = "forming"
        if last_close < mid - buffer:
            status, breakout_date = "confirmed_breakout_down", dates[-1]
    else:
        status = "forming"
        if last_close > mid + buffer:
            status, breakout_date = "confirmed_breakout_up", dates[-1]

    fit_quality = max(
        0.0, 1 - diff_pct / diff_tolerance
    )  # tighter-matched peaks/troughs score higher
    depth_quality = min(
        1.0, retrace_pct / retrace_tolerance
    )  # a deeper, cleaner pullback scores higher
    strength = 45 + 25 * fit_quality + 20 * depth_quality
    if len(idxs) >= 3:
        strength += 5  # a third same-direction pivot further back is corroborating context

    pivots = [
        PatternPoint(date=dates[i1], price=v1, kind="high" if top else "low"),
        PatternPoint(date=dates[i2], price=v2, kind="high" if top else "low"),
    ]
    return PatternMatch(
        pattern_type="double_top" if top else "double_bottom",
        status=status,
        start_date=dates[i1],
        end_date=breakout_date or dates[-1],
        breakout_date=breakout_date,
        pivots=pivots,
        key_levels=[round(mid, 2)],
        strength_score=round(min(max(strength, 0.0), 100.0), 1),
        touches_resistance=2 if top else 0,
        touches_support=0 if top else 2,
    )


def detect_patterns(
    bars: Sequence[BarLike], *, pivot_k: int = 5, lookback: int = LOOKBACK
) -> list[PatternMatch]:
    """Detect the single strongest currently-active chart pattern from daily bars (any order).

    Returns at most one match — a stock flagged for several overlapping shapes at once is noise,
    not a clearer signal, so callers get one pattern per stock, not a pile of maybe-matches.
    """
    rows = sorted(bars, key=lambda b: b.date)
    if len(rows) > lookback:
        rows = rows[-lookback:]
    n = len(rows)
    if n < 4 * pivot_k + 10:
        return []

    highs = [b.high for b in rows]
    lows = [b.low for b in rows]
    closes = [b.close for b in rows]
    dates = [b.date for b in rows]
    atr14 = atr(highs, lows, closes, 14)

    sh_idx = swing_high_indices(highs, pivot_k)
    sl_idx = swing_low_indices(lows, pivot_k)

    candidates: list[PatternMatch] = []
    flat_base = _flat_base_match(rows)
    if flat_base is not None:
        candidates.append(flat_base)
    tri = _detect_triangle_channel(sh_idx, sl_idx, highs, lows, closes, dates, atr14, n)
    if tri is not None:
        candidates.append(tri)
    dtop = _detect_double(sh_idx, highs, lows, closes, dates, atr14, top=True)
    if dtop is not None:
        candidates.append(dtop)
    dbot = _detect_double(sl_idx, lows, highs, closes, dates, atr14, top=False)
    if dbot is not None:
        candidates.append(dbot)

    passing = [c for c in candidates if c.strength_score >= MIN_STRENGTH]
    if not passing:
        return []
    return [max(passing, key=lambda c: c.strength_score)]
