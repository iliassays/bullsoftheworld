"""Shared market-data freshness classification for quote-derived API surfaces."""

from __future__ import annotations

import datetime as dt

from bulls.market_data.calendar import market_close_on, session_phase, to_market_tz


def quote_data_status(
    now: dt.datetime,
    market: str,
    quote_as_of: dt.datetime | None,
    close_as_of_date: dt.date | None,
) -> str:
    """Describe what a quote/close mixture represents without calling prior-close data live."""

    if now.tzinfo is None:
        raise ValueError("market data status requires a timezone-aware current time")
    phase = str(session_phase(now, market=market))
    if quote_as_of is None:
        return "stale" if phase == "open" else "official_close"
    if quote_as_of.tzinfo is None:
        quote_as_of = quote_as_of.replace(tzinfo=dt.UTC)
    local_now = to_market_tz(now, market=market)
    local_quote = to_market_tz(quote_as_of, market=market)
    quote_date = local_quote.date()
    if phase == "open" and (
        quote_date != local_now.date() or (now - quote_as_of).total_seconds() > 35 * 60
    ):
        return "stale"
    quote_leads_close = close_as_of_date is None or quote_date > close_as_of_date
    if quote_date == local_now.date() and quote_leads_close:
        if phase == "open":
            return "intraday_delayed"
        if phase == "post_close" and local_quote.time() < market_close_on(quote_date, market):
            return "stale"
        return "provisional_close"
    return "official_close"
