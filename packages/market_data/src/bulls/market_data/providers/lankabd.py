"""LankaBD block-market page — the per-scrip block-trade list DSE itself doesn't publish.

⚠ INTERNAL-ONLY source (2026-07-03): lankabd.com is a brokerage portal, not the exchange; the
sourcing/ToS question is open (docs/redesign/2026-07-drops.md). One request per trading day,
data feeds the admin view only — nothing public renders from it until that decision is made.

The page is two Bootstrap tab panes (#dse / #cse); we parse the DSE pane only. Row shape:
symbol anchor + Quantity / Value(MN) / Trades / Max / Min right-aligned cells; the trade date
rides in a date-named input's value attribute.
"""

from __future__ import annotations

import datetime as dt
import re

import httpx
from pydantic import BaseModel

_URL = "https://lankabd.com/Home/BlockMarket"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BullsOfDhaka-internal/1.0)"}
_TIMEOUT = 30.0

_ROW_RE = re.compile(
    r'<a class="indigo-text"[^>]*>([A-Z0-9.&()-]+)</a>.*?'
    r'<td class="text-right">([\d,]+)</td>\s*'
    r'<td class="text-right">([\d,.]+)</td>\s*'
    r'<td class="text-right">(\d+)</td>\s*'
    r'<td class="text-right">([\d,.]+)</td>\s*'
    r'<td class="text-right">([\d,.]+)</td>',
    re.S,
)
_DATE_RE = re.compile(r'id="[^"]*[Dd]ate[^"]*"[^>]*value="(\d{4}-\d{2}-\d{2})"')


class BlockTradeRow(BaseModel):
    code: str
    trade_date: dt.date
    quantity: int
    value_mn: float
    trades: int
    max_price: float | None
    min_price: float | None


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def parse_block_market(html: str) -> list[BlockTradeRow]:
    """Pure parse (unit-testable offline): DSE pane rows + the page's trade date."""
    date_m = _DATE_RE.search(html)
    if not date_m:
        return []  # no date = can't stamp freshness honestly = omit over mislead
    trade_date = dt.date.fromisoformat(date_m.group(1))

    # Only the DSE tab pane — the CSE table repeats the same column shape after it.
    dse_start = html.find('id="dse"')
    cse_start = html.find('id="cse"')
    pane = (
        html[dse_start : cse_start if cse_start > dse_start else None] if dse_start >= 0 else html
    )

    rows = []
    for m in _ROW_RE.finditer(pane):
        code, qty, value, trades, mx, mn = m.groups()
        rows.append(
            BlockTradeRow(
                code=code.strip().upper(),
                trade_date=trade_date,
                quantity=int(_num(qty)),
                value_mn=_num(value),
                trades=int(trades),
                max_price=_num(mx),
                min_price=_num(mn),
            )
        )
    return rows


async def fetch_block_trades() -> list[BlockTradeRow]:
    async with httpx.AsyncClient(headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True) as c:
        r = await c.get(_URL)
        r.raise_for_status()
        return parse_block_market(r.text)
