"""Market-update agent: one daily market-wide wrap (DSEX + breadth + turnover).

Not tied to a ticker, so it carries no cashtag — it shows in the home feed and the global Bulls
feed, not on a symbol page. Descriptive close summary, no advice.
"""

from __future__ import annotations

from bulls.analytics.indicators import index_change_pct
from bulls.core.markets import get_market_profile
from bulls.core.models import MarketSummary

BEAT = "market"
MARKET_CODE = "MARKET"  # ledger code for the market-wide note (no cashtag)


def render(summary: MarketSummary, advancers: int, decliners: int, locale: str) -> str:
    profile = get_market_profile(summary.market)
    if summary.market == "DSE":
        level = f"{summary.dsex:,.0f}" if summary.dsex is not None else "—"
        # dsex_change is the POINT change from the DSE summary page.
        pct = index_change_pct(summary.dsex, summary.dsex_change)
        turnover = (
            f"৳{summary.total_value_mn / 10:,.0f} Cr"
            if summary.total_value_mn is not None
            else "—"
        )
    else:
        level = (
            f"{summary.benchmark_close:,.2f}"
            if summary.benchmark_close is not None
            else "—"
        )
        prior = (
            summary.benchmark_close - summary.benchmark_change
            if summary.benchmark_close is not None and summary.benchmark_change is not None
            else None
        )
        pct = (
            summary.benchmark_change / prior * 100
            if prior is not None and prior > 0 and summary.benchmark_change is not None
            else None
        )
        turnover = (
            f"${summary.total_value_mn / 1_000:,.1f}B estimated traded value"
            if summary.total_value_mn is not None
            else "—"
        )
    chg = f"{pct:+.2f}%" if pct is not None else "—"
    benchmark = profile.benchmark_label
    if locale == "bn":
        return (
            f"📊 বাজার ক্লোজ: {benchmark} {level} ({chg}) · {advancers}টি বেড়েছে / "
            f"{decliners}টি কমেছে · টার্নওভার {turnover}। তথ্যমূলক, পরামর্শ নয়।"
        )
    return (
        f"📊 Market close: {benchmark} {level} ({chg}) · {advancers} advancers / "
        f"{decliners} decliners · {turnover}. Descriptive, not advice."
    )
