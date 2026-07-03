"""Market-update agent: one daily market-wide wrap (DSEX + breadth + turnover).

Not tied to a ticker, so it carries no cashtag — it shows in the home feed and the global Bulls
feed, not on a symbol page. Descriptive close summary, no advice.
"""

from __future__ import annotations

from bulls.analytics.indicators import index_change_pct
from bulls.core.models import MarketSummary

BEAT = "market"
MARKET_CODE = "MARKET"  # ledger code for the market-wide note (no cashtag)


def render(summary: MarketSummary, advancers: int, decliners: int, locale: str) -> str:
    dsex = f"{summary.dsex:,.0f}" if summary.dsex is not None else "—"
    # dsex_change is the POINT change from the DSE summary page — convert before adding a % sign
    pct = index_change_pct(summary.dsex, summary.dsex_change)
    chg = f"{pct:+.2f}%" if pct is not None else "—"
    cr = f"৳{summary.total_value_mn / 10:,.0f} Cr" if summary.total_value_mn is not None else "—"
    if locale == "bn":
        return (
            f"📊 বাজার ক্লোজ: DSEX {dsex} ({chg}) · {advancers}টি বেড়েছে / {decliners}টি কমেছে · "
            f"টার্নওভার {cr}। তথ্যমূলক, পরামর্শ নয়।"
        )
    return (
        f"📊 Market close: DSEX {dsex} ({chg}) · {advancers} advancers / {decliners} decliners · "
        f"turnover {cr}. Descriptive, not advice."
    )
