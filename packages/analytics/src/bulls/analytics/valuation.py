"""Derive daily valuation from today's close + slow-moving fundamentals.

Market cap, float cap, P/E, P/B and dividend yield all move with price, so they must be recomputed
each day — but their inputs (shares, EPS, NAV, dividend) change only quarterly/annually and come from
the weekly company scrape. So we compute, never scrape, these: accurate to our own close, zero extra
load on the source. Pure + I/O-free; inputs are plain scalars (no dependency on market_data).
"""

from __future__ import annotations

from pydantic import BaseModel


class ValuationResult(BaseModel):
    market_cap_mn: float | None = None
    free_float_cap_mn: float | None = None
    pe_ratio: float | None = None  # None when EPS <= 0 (loss-making) — a P/E would be meaningless
    pb_ratio: float | None = None
    dividend_yield: float | None = None  # % — cash dividend (taka) / close
    roe: float | None = None  # % — return on equity, EPS / NAV-per-share


def _r(x: float | None, n: int = 2) -> float | None:
    return None if x is None else round(x, n)


def compute_valuation(
    last_close: float,
    *,
    outstanding_shares: int | None = None,
    market_cap_mn_ref: float | None = None,
    free_float_mcap_mn_ref: float | None = None,
    eps: float | None = None,
    nav_per_share: float | None = None,
    cash_dividend_pct: float | None = None,
    cash_dividend_per_share: float | None = None,
    face_value: float | None = None,
) -> ValuationResult:
    """Valuation for one symbol. `*_ref` are scrape-time values used only for the float ratio."""
    if not last_close or last_close <= 0:
        return ValuationResult()

    market_cap_mn = last_close * outstanding_shares / 1e6 if outstanding_shares else None

    # Free-float fraction is stable; scale today's market cap by it rather than trusting a stale cap.
    free_float_cap_mn = None
    if market_cap_mn and market_cap_mn_ref and free_float_mcap_mn_ref and market_cap_mn_ref > 0:
        free_float_cap_mn = market_cap_mn * (free_float_mcap_mn_ref / market_cap_mn_ref)

    pe_ratio = last_close / eps if eps and eps > 0 else None
    pb_ratio = last_close / nav_per_share if nav_per_share and nav_per_share > 0 else None
    # Return on equity = profit/equity = (profit/shares) / (equity/shares) = EPS / NAV-per-share.
    # NAV floored at ৳1 to avoid a tiny denominator exploding ROE on distressed names.
    roe = (
        eps / nav_per_share * 100
        if eps is not None and nav_per_share and nav_per_share >= 1
        else None
    )

    dividend_yield = None
    cash_amount = cash_dividend_per_share
    if cash_amount is None and cash_dividend_pct is not None and face_value:
        cash_amount = cash_dividend_pct / 100 * face_value
    if cash_amount is not None:
        # Preserve the observed trailing yield. An unusually high value can be a price-collapse or
        # payout-sustainability warning, but suppressing it turns a calculable fact into missing data.
        dividend_yield = cash_amount / last_close * 100

    return ValuationResult(
        market_cap_mn=_r(market_cap_mn),
        free_float_cap_mn=_r(free_float_cap_mn),
        pe_ratio=_r(pe_ratio),
        pb_ratio=_r(pb_ratio),
        dividend_yield=_r(dividend_yield),
        roe=_r(roe),
    )
