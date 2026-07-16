"""Hedge — a tiny standalone web app for the daily trading list.

Separate from the Bulls social portal: this is your private morning tool. One page, server-rendered
from the same database + the validated Scheme-3 scan. No build step.

    uv run python scripts/hedge_app.py        # then open http://127.0.0.1:8100
    uv run python scripts/hedge_app.py --port 9000

JSON too: http://127.0.0.1:8100/api/signals
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import time
from collections import defaultdict

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from hedge_daily import scan
from hedge_forward import read_log, render_ledger
from hedge_history import read_snapshot, render_history
from risk_calc import MAX_HEAT_PCT, MAX_POSITION_PCT, MAX_POSITIONS, size
from sqlalchemy import select

from bulls.analytics import STRATEGIES, calculate_agent_performance
from bulls.core.db import bind_tenant_context, get_sessionmaker
from bulls.core.models import (
    AgentLot,
    AgentPortfolio,
    AgentTrade,
    PortfolioHolding,
    QuoteSnapshot,
    User,
)
from bulls.market_data.calendar import to_market_tz

app = FastAPI(title="Hedge")

# The market data only changes once a day (after EOD), but the scan + backtest are expensive
# (~2s each: load every bar, recompute Scheme-3). Cache results in-process so navigating the app
# is instant; a short TTL means it still picks up the day's new bars without a restart. Per-key
# locks stop two concurrent loads from both doing the heavy work.
_CACHE: dict[object, tuple[float, object]] = {}
_LOCKS: dict[object, asyncio.Lock] = {}
_TTL = 600  # seconds


async def _cached(key, factory):
    hit = _CACHE.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    async with _LOCKS.setdefault(key, asyncio.Lock()):
        hit = _CACHE.get(key)  # another request may have filled it while we waited for the lock
        if hit and hit[0] > time.monotonic():
            return hit[1]
        val = await factory()
        _CACHE[key] = (time.monotonic() + _TTL, val)
        return val


_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0f1115;color:#e6e8eb;
  line-height:1.5;padding:16px;max-width:860px;margin:0 auto}
h1{font-size:22px;font-weight:600;letter-spacing:-.5px}
.sub{color:#8b909a;font-size:13px;margin-top:2px}
.tr{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0;padding:12px;background:#171a21;border-radius:12px}
.tr div{flex:1;min-width:90px}
.tr .k{font-size:11px;color:#8b909a;text-transform:uppercase;letter-spacing:.5px}
.tr .v{font-size:18px;font-weight:600;margin-top:2px}
.pos{color:#3ddc84}.neg{color:#ff6b6b}
h2{font-size:14px;margin:22px 0 10px;color:#b6bbc4;font-weight:600}
.card{background:#171a21;border:1px solid #232733;border-radius:12px;padding:14px;margin-bottom:10px}
.card .top{display:flex;justify-content:space-between;align-items:baseline}
.tk{font-size:18px;font-weight:700}
.tag{font-size:11px;color:#8b909a;background:#232733;padding:2px 8px;border-radius:20px}
.lvl{display:flex;gap:14px;margin:10px 0 6px}
.lvl div .k{font-size:11px;color:#8b909a}
.lvl div .v{font-size:16px;font-weight:600}
.why{font-size:13px;color:#9aa0aa}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 6px;border-bottom:1px solid #232733}
th{color:#8b909a;font-weight:500;font-size:11px;text-transform:uppercase}
.foot{margin-top:22px;font-size:12px;color:#7a7f88;border-top:1px solid #232733;padding-top:12px}
.empty{color:#8b909a;font-style:italic;padding:8px 0}
nav{display:flex;gap:8px;margin:12px 0 4px}
nav a{font-size:13px;color:#b6bbc4;text-decoration:none;padding:6px 14px;border:1px solid #232733;
  border-radius:20px}
nav a.on{background:#1f2a22;color:#3ddc84;border-color:#2a5a3f}
.chart{width:100%;height:auto;margin:6px 0}
.chart .grid{stroke:#2a2f3a;stroke-width:1}
.chart .ax{fill:#6b7280;font-size:11px;text-anchor:middle}
.cap{font-size:12px;color:#7a7f88;margin:4px 0 8px}
.scroll{max-height:440px;overflow-y:auto;border:1px solid #232733;border-radius:10px}
.scroll table{font-variant-numeric:tabular-nums}
.scroll th{position:sticky;top:0;background:#171a21}
.win{color:#3ddc84}.loss{color:#ff6b6b}
.pill{font-size:11px;padding:1px 8px;border-radius:20px;background:#232733;color:#9aa0aa}
.pill.win{background:#16321f;color:#3ddc84}.pill.loss{background:#3a1e1e;color:#ff6b6b}
form.sz{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin:14px 0}
form.sz label{font-size:11px;color:#8b909a;text-transform:uppercase;letter-spacing:.5px;display:block}
form.sz input{background:#0f1115;border:1px solid #232733;color:#e6e8eb;border-radius:8px;
  padding:8px 10px;font-size:15px;width:130px;margin-top:4px}
form.sz button{background:#1f2a22;color:#3ddc84;border:1px solid #2a5a3f;border-radius:8px;
  padding:9px 18px;font-size:14px;cursor:pointer}
td.num{text-align:right;font-variant-numeric:tabular-nums}
"""


def _shell(active: str, body: str) -> str:
    def tab(href, label):
        return f'<a href="{href}" class="{"on" if active == href else ""}">{label}</a>'

    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Hedge</title>
<style>{_CSS}</style></head><body>
<h1>Hedge <span style="color:#3ddc84">·</span></h1>
<nav>{tab("/", "Today's list")}{tab("/sizing", "Risk / sizing")}{tab("/history", "Track record")}{tab("/portfolios", "Agent portfolios")}</nav>
{body}
</body></html>"""


def _render(d: dict) -> str:
    tr = d["track_record"]
    buys = (
        "".join(
            f"""<div class="card"><div class="top"><span class="tk">{x["code"]}</span>
        <span class="tag">{x["sector"]}</span></div>
        <div class="lvl">
          <div><div class="k">entry</div><div class="v">{x["price"]}</div></div>
          <div><div class="k">stop</div><div class="v neg">{x["stop"]}</div></div>
          <div><div class="k">target</div><div class="v pos">{x["target"]}</div></div>
          <div><div class="k">P/E · ROE</div><div class="v">{x["pe"]} · {x["roe"]}%</div></div>
        </div>
        <div class="why">washed-out {x["below_high"]}% off its high · cheap + profitable · fired {x["fired_on"]}</div>
        </div>"""
            for x in d["fired"]
        )
        or '<div class="empty">No buy signals today — the strategy is selective. Check the watchlist.</div>'
    )

    watch = (
        "".join(
            f"<tr><td><b>{x['code']}</b></td><td>{x['price']}</td><td>{x['pe']}</td>"
            f"<td>{x['roe']}%</td><td>{x['below_high']}%</td><td>{x['sector']}</td></tr>"
            for x in d["watch"]
        )
        or '<tr><td colspan="6" class="empty">Nothing set up right now.</td></tr>'
    )

    return f"""
<div class="sub">Daily list · as of EOD {d["as_of"]} · delayed data · for your own use, not advice</div>
<div class="tr">
  <div><div class="k">Backtest 2yr</div><div class="v pos">+{tr["total_2y"]}%</div></div>
  <div><div class="k">vs market</div><div class="v">+{tr["index_2y"]}%</div></div>
  <div><div class="k">win rate</div><div class="v">{tr["win"]}%</div></div>
  <div><div class="k">worst drop</div><div class="v neg">{tr["maxdd"]}%</div></div>
</div>
<h2>BUY signals ({len(d["fired"])})</h2>
{buys}
<h2>Watchlist — set up, waiting for the turn ({len(d["watch"])})</h2>
<table><tr><th>code</th><th>price</th><th>P/E</th><th>ROE</th><th>off high</th><th>sector</th></tr>
{watch}</table>
<div class="foot">Hold ~2 weeks to 3 months · exit at target (+25%), stop (-10%), or 3 months ·
risk ~1-2% of capital per name, ~10 positions. Single-regime backtest, EOD data - trade small,
the stop is mandatory.</div>"""


def render_sizing(d: dict, capital: float, risk: float, held: int) -> str:
    r = size(capital, risk, d["fired"], held=held)
    rows, invested, heat, reserved = r["rows"], r["invested"], r["heat"], r["reserved"]
    pct = lambda x: x / capital * 100 if capital else 0  # noqa: E731
    body = (
        "".join(
            f"<tr><td><b>{x['code']}</b></td><td class='num'>{x['score'] or 0}</td>"
            f"<td class='num'>{x['entry']:.1f}</td>"
            f"<td class='num neg'>{x['stop']:.1f}</td><td class='num pos'>{x['target']:.1f}</td>"
            f"<td class='num'>{x['shares']:,}</td><td class='num'>{x['invested']:,.0f}</td>"
            f"<td class='num'>{x['risk']:,.0f}</td><td class='num pos'>{x['reward']:,.0f}</td></tr>"
            for x in rows
        )
        or f'<tr><td colspan="9" class="empty">No free slots — you already hold {held} of {MAX_POSITIONS}. Wait for an exit.</td></tr>'
    )
    wait = (
        '<div class="cap"><b>Waitlist</b> (no room today — take when an open position exits): '
        + ", ".join(f"{s['code']} ({s['score']})" for s in r["waitlist"])
        + "</div>"
        if r["waitlist"]
        else ""
    )
    ref = "".join(
        f"<tr><td class='num'>{rp:.2f}%</td><td class='num'>{rp * 10:.0f}%</td>"
        f"<td class='num'>{min(MAX_POSITIONS, int(MAX_HEAT_PCT / rp))}</td>"
        f"<td class='num'>{min(MAX_HEAT_PCT, min(MAX_POSITIONS, int(MAX_HEAT_PCT / rp)) * rp):.0f}%</td></tr>"
        for rp in (0.5, 1.0, 1.5, 2.0)
    )
    return f"""
<div class="sub">Sizing the buy list · holding {held}, {r["free"]} of {MAX_POSITIONS} slots free · fund {len(rows)}, waitlist {len(r["waitlist"])} · EOD {d["as_of"]}</div>
<form class="sz" method="get" action="/sizing">
  <div><label>Capital (BDT)</label><input name="capital" type="number" value="{capital:.0f}" step="1000"></div>
  <div><label>Risk per trade %</label><input name="risk" type="number" value="{risk:g}" step="0.25" min="0.25" max="3"></div>
  <div><label>Positions open</label><input name="held" type="number" value="{held}" step="1" min="0" max="{MAX_POSITIONS}"></div>
  <button type="submit">Recalculate</button>
</form>
<div class="tr">
  <div><div class="k">New cash to deploy</div><div class="v">{invested:,.0f}</div></div>
  <div><div class="k">Cash left after</div><div class="v">{capital - reserved - invested:,.0f}</div></div>
  <div><div class="k">Total at risk (heat)</div><div class="v neg">{heat:,.0f}<span style="font-size:12px;color:#8b909a"> ({pct(heat):.1f}%)</span></div></div>
  <div><div class="k">Positions after</div><div class="v">{held + len(rows)} / {MAX_POSITIONS}</div></div>
</div>
<table>
<tr><th>code</th><th class="num">conv</th><th class="num">entry</th><th class="num">stop</th><th class="num">target</th>
<th class="num">shares</th><th class="num">invest ৳</th><th class="num">risk ৳</th><th class="num">reward ৳</th></tr>
{body}</table>
{wait}
<div class="cap">"At risk" = your total loss if every open trade (held + new) stops out at once. Each name is
sized so a stop-out costs ~{risk:g}% of capital; capped at {MAX_POSITION_PCT:.0f}% per name and {MAX_HEAT_PCT:.0f}% total.
You never hold more than {MAX_POSITIONS} — extra signals wait for a slot to free, which is why a fresh
batch can never demand money you don't have. "conv" = the strategy's conviction rank (fund the top first).</div>
<h2>How many names? (risk % sets it automatically)</h2>
<table>
<tr><th class="num">risk/trade</th><th class="num">position size</th><th class="num">max names</th><th class="num">portfolio max loss</th></tr>
{ref}</table>
<div class="foot">Lower the risk % for smaller positions across more names (more diversification); raise it
for fewer, bigger ones. The DSE ~10% circuit breaker makes the -10% stop reliable — over the 2-year
backtest no trade lost more than the stop, so "{risk:g}% at risk" holds up. Delayed EOD data · your own use, not advice.</div>"""


async def _agent_book() -> list[dict]:
    """All agent portfolios from six bulk queries, priced against the latest DSE quotes."""
    tenant_id, market = "bullsofdhaka", "DSE"
    today = to_market_tz(dt.datetime.now(dt.UTC), market=market).date()
    out: list[dict] = []
    async with get_sessionmaker()() as session:
        await bind_tenant_context(session, tenant_id)
        rows = (
            await session.execute(
                select(AgentPortfolio, User)
                .join(User, User.id == AgentPortfolio.user_id)
                .where(
                    AgentPortfolio.market == market,
                    User.tenant_id == tenant_id,
                )
            )
        ).all()
        user_ids = [agent.user_id for agent, _ in rows]
        if not user_ids:
            return out

        holdings = (
            await session.scalars(
                select(PortfolioHolding).where(
                    PortfolioHolding.tenant_id == tenant_id,
                    PortfolioHolding.market == market,
                    PortfolioHolding.user_id.in_(user_ids),
                )
            )
        ).all()
        lots = (
            await session.scalars(
                select(AgentLot).where(
                    AgentLot.market == market,
                    AgentLot.user_id.in_(user_ids),
                    AgentLot.quantity_left > 0,
                )
            )
        ).all()
        all_trades = (
            await session.scalars(
                select(AgentTrade)
                .where(AgentTrade.market == market, AgentTrade.user_id.in_(user_ids))
                .order_by(AgentTrade.user_id, AgentTrade.id)
            )
        ).all()
        codes = sorted({holding.code for holding in holdings})
        quotes = {
            q.code: q
            for q in (
                await session.scalars(
                    select(QuoteSnapshot).where(
                        QuoteSnapshot.market == market,
                        QuoteSnapshot.code.in_(codes or [""]),
                    )
                )
            ).all()
        }

        holdings_by_user: dict[int, list] = defaultdict(list)
        lots_by_user: dict[int, list] = defaultdict(list)
        trades_by_user: dict[int, list] = defaultdict(list)
        for holding in holdings:
            holdings_by_user[holding.user_id].append(holding)
        for lot in lots:
            lots_by_user[lot.user_id].append(lot)
        for trade in all_trades:
            trades_by_user[trade.user_id].append(trade)

        for agent, user in sorted(rows, key=lambda row: row[1].handle):
            spec = STRATEGIES[agent.strategy]
            agent_holdings = holdings_by_user[agent.user_id]
            agent_trades = trades_by_user[agent.user_id]
            matured: dict[str, int] = {}
            for lot in lots_by_user[agent.user_id]:
                if lot.sellable_from <= today:
                    matured[lot.code] = matured.get(lot.code, 0) + lot.quantity_left
            pending = sum(
                trade.net_cash
                for trade in agent_trades
                if trade.side == "sell" and not trade.settled
            )
            prices = {
                holding.code: quotes[holding.code].ltp
                for holding in agent_holdings
                if holding.code in quotes and quotes[holding.code].ltp is not None
            }
            performance = calculate_agent_performance(agent_trades, prices)

            hout, value_known, total_value = [], True, 0.0
            quote_times = []
            for h in agent_holdings:
                q = quotes.get(h.code)
                if q is None or q.ltp is None:
                    value_known = False
                else:
                    total_value += h.quantity * q.ltp
                    quote_times.append(q.as_of)
                hout.append(
                    {
                        "code": h.code,
                        "qty": h.quantity,
                        "sellable": min(matured.get(h.code, 0), h.quantity),
                        "avg": h.avg_cost,
                        "ltp": q.ltp if q else None,
                        "pnl_pct": (
                            (q.ltp - h.avg_cost) / h.avg_cost * 100
                            if q and h.avg_cost > 0
                            else None
                        ),
                    }
                )
            equity = agent.cash_settled + pending + total_value if value_known else None
            out.append(
                {
                    "handle": user.handle,
                    "display": spec.display_name,
                    "desc": spec.description,
                    "cash": agent.cash_settled,
                    "pending": pending,
                    "capital": agent.initial_capital,
                    "equity": equity,
                    "pnl": equity - agent.initial_capital if equity is not None else None,
                    "return_pct": (
                        (equity / agent.initial_capital - 1) * 100
                        if equity is not None and agent.initial_capital
                        else None
                    ),
                    "realized_pnl": performance.realized_pnl,
                    "unrealized_pnl": performance.unrealized_pnl,
                    "fees": performance.fees,
                    "closed_trades": performance.closed_trades,
                    "win_rate": performance.win_rate,
                    "quotes_as_of": min(quote_times) if quote_times else None,
                    "holdings": hout,
                    "trades": list(reversed(agent_trades[-200:])),
                }
            )
    return out


def _fmt_tk(v: float | None) -> str:
    return "—" if v is None else f"{v:,.0f}"


def _fmt_pct(v: float | None) -> str:
    return "—" if v is None else f"{v:+.2f}%"


def render_portfolios(book: list[dict], selected: str) -> str:
    chosen = next((a for a in book if a["handle"] == selected), None)
    options = "".join(
        f'<option value="{a["handle"]}" {"selected" if a["handle"] == selected else ""}>'
        f"{a['display']}</option>"
        for a in book
    )
    combo = f"""<form class="sz" method="get" action="/portfolios">
      <div><label>Portfolio</label>
      <select name="p" onchange="this.form.submit()" style="background:#0f1115;border:1px solid #232733;
        color:#e6e8eb;border-radius:8px;padding:8px 10px;font-size:15px;margin-top:4px">
      <option value="">All agents — overview</option>{options}</select></div></form>"""

    if chosen is None:  # overview table of the whole stable
        rows = (
            "".join(
                f"<tr><td><b>{a['display']}</b></td>"
                f"<td class='num'>{_fmt_tk(a['equity'])}</td>"
                f"<td class='num {'pos' if (a['pnl'] or 0) >= 0 else 'neg'}'>{_fmt_tk(a['pnl'])}</td>"
                f"<td class='num'>{_fmt_tk(a['cash'])}</td>"
                f"<td class='num'>{_fmt_tk(a['pending'])}</td>"
                f"<td class='num'>{len(a['holdings'])}</td>"
                f"<td class='num'>{_fmt_pct(a['return_pct'])}</td></tr>"
                for a in book
            )
            or '<tr><td colspan="7" class="empty">No agent portfolios seeded.</td></tr>'
        )
        total_eq = sum(a["equity"] or 0 for a in book)
        total_cap = sum(a["capital"] for a in book)
        return f"""{combo}
<div class="sub">Simulated ৳1-lac model portfolios, traded automatically every 15 min with DSE T+2
settlement · paper trading on delayed quotes · not advice</div>
<div class="tr">
  <div><div class="k">Combined equity</div><div class="v">{total_eq:,.0f}</div></div>
  <div><div class="k">vs deployed</div><div class="v {"pos" if total_eq >= total_cap else "neg"}">{total_eq - total_cap:+,.0f}</div></div>
</div>
<table><tr><th>portfolio</th><th class="num">equity ৳</th><th class="num">P&L ৳</th>
<th class="num">cash ৳</th><th class="num">settling ৳</th><th class="num">positions</th><th class="num">return</th></tr>
{rows}</table>
<div class="foot">Pick a portfolio above for its holdings and full trade log. "Settling" = sell
proceeds still inside the T+2 window — real money, not yet spendable. Full detail incl. reasons
also lives in the portal cockpit.</div>"""

    holds = (
        "".join(
            f"<tr><td><b>{h['code']}</b></td><td class='num'>{h['qty']:,}</td>"
            f"<td class='num'>{h['sellable']:,}</td><td class='num'>{h['avg']:.2f}</td>"
            f"<td class='num'>{h['ltp'] if h['ltp'] is not None else '—'}</td>"
            f"<td class='num {'pos' if (h['pnl_pct'] or 0) >= 0 else 'neg'}'>"
            f"{f'{h["pnl_pct"]:+.1f}%' if h['pnl_pct'] is not None else '—'}</td></tr>"
            for h in chosen["holdings"]
        )
        or '<tr><td colspan="6" class="empty">No open positions — all cash.</td></tr>'
    )
    trades = (
        "".join(
            f"<tr><td>{t.trade_date}</td>"
            f"<td><span class='pill {'win' if t.side == 'buy' else 'loss'}'>{t.side}</span></td>"
            f"<td><b>{t.code}</b></td><td class='num'>{t.quantity:,}</td>"
            f"<td class='num'>{t.price:.2f}</td><td class='num'>{t.fee:.2f}</td>"
            f"<td>{t.settles_on}{'' if t.settled or t.side == 'buy' else ' · pending'}</td>"
            f"<td class='why'>{t.reason}</td></tr>"
            for t in chosen["trades"]
        )
        or '<tr><td colspan="8" class="empty">No trades yet.</td></tr>'
    )
    pnl = chosen["pnl"]
    return f"""{combo}
<div class="sub">{chosen["display"]} · @{chosen["handle"]} · {chosen["desc"]}</div>
<div class="tr">
  <div><div class="k">Equity</div><div class="v">{_fmt_tk(chosen["equity"])}</div></div>
  <div><div class="k">P&L</div><div class="v {"pos" if (pnl or 0) >= 0 else "neg"}">{_fmt_tk(pnl)}</div></div>
  <div><div class="k">Cash</div><div class="v">{_fmt_tk(chosen["cash"])}</div></div>
  <div><div class="k">Settling</div><div class="v">{_fmt_tk(chosen["pending"])}</div></div>
  <div><div class="k">Positions</div><div class="v">{len(chosen["holdings"])}</div></div>
</div>
<div class="tr">
  <div><div class="k">Realized P&L</div><div class="v {"pos" if chosen["realized_pnl"] >= 0 else "neg"}">{chosen["realized_pnl"]:+,.0f}</div></div>
  <div><div class="k">Unrealized P&L</div><div class="v {"pos" if (chosen["unrealized_pnl"] or 0) >= 0 else "neg"}">{_fmt_tk(chosen["unrealized_pnl"])}</div></div>
  <div><div class="k">Closed trades</div><div class="v">{chosen["closed_trades"]}</div></div>
  <div><div class="k">Win rate</div><div class="v">{f"{chosen['win_rate']:.1f}%" if chosen["win_rate"] is not None else "Not established"}</div></div>
  <div><div class="k">Fees paid</div><div class="v">{chosen["fees"]:,.0f}</div></div>
</div>
<div class="cap">Oldest quote in this valuation: {chosen["quotes_as_of"] or "no open positions"}.
Returns are mark-to-market; a win rate appears only after positions have been sold.</div>
<h2>Holdings</h2>
<table><tr><th>code</th><th class="num">qty</th><th class="num">sellable</th>
<th class="num">avg cost</th><th class="num">ltp</th><th class="num">P&L</th></tr>
{holds}</table>
<h2>Trade log ({len(chosen["trades"])})</h2>
<div class="scroll"><table>
<tr><th>date</th><th>side</th><th>code</th><th class="num">qty</th><th class="num">price</th>
<th class="num">fee</th><th>settles</th><th>reason</th></tr>
{trades}</table></div>
<div class="foot">"Sellable" counts only shares past T+2 settlement — the engine cannot sell the
rest yet, whatever the price does. Every fill is at the delayed last-traded price + 0.4% brokerage.
Paper trading · not advice.</div>"""


async def _scan(days: int):  # shared by Today's-list and Sizing — computed once per TTL
    return await _cached(("scan", days), lambda: scan(days))


async def _history_body() -> str:
    snapshot = await read_snapshot()
    if snapshot is None:
        return """<h2>Track record is preparing</h2>
<div class="card"><div class="why">The batch snapshot has not completed yet. This page never runs
the multi-year backtest inside your browser request; refresh after the scheduled EOD job.</div></div>"""
    return render_history(
        snapshot.payload,
        computed_at=snapshot.computed_at,
        as_of_date=snapshot.as_of_date,
    ) + render_ledger(await read_log())


@app.get("/", response_class=HTMLResponse)
async def home(days: int = 10):  # ~2 weeks of recent fires for the morning view
    return _shell("/", _render(await _scan(days)))


@app.get("/sizing", response_class=HTMLResponse)
async def sizing(capital: float = 200_000, risk: float = 1.0, held: int = 0, days: int = 10):
    risk = min(max(risk, 0.25), 3.0)  # keep the knob in a sane band
    held = min(max(held, 0), MAX_POSITIONS)
    return _shell("/sizing", render_sizing(await _scan(days), capital, risk, held))


@app.get("/history", response_class=HTMLResponse)
async def history():
    return _shell("/history", await _cached("history", _history_body))


@app.get("/portfolios", response_class=HTMLResponse)
async def portfolios(p: str = ""):
    return _shell("/portfolios", render_portfolios(await _agent_book(), p))


@app.get("/api/portfolios")
async def api_portfolios():
    book = await _agent_book()
    for a in book:  # ORM rows aren't JSON-serializable; flatten the essentials
        a["trades"] = [
            {
                "date": str(t.trade_date),
                "side": t.side,
                "code": t.code,
                "qty": t.quantity,
                "price": t.price,
                "fee": t.fee,
                "settles_on": str(t.settles_on),
                "settled": t.settled,
                "reason": t.reason,
            }
            for t in a["trades"]
        ]
    return book


@app.get("/api/signals")
async def api(days: int = 5):
    return await _scan(days)


def main():
    import os

    from granian import Granian

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8100)
    args = ap.parse_args()
    os.chdir(
        os.path.dirname(os.path.abspath(__file__))
    )  # so granian workers can import this module
    print(f"Hedge running -> http://127.0.0.1:{args.port}  (Ctrl-C to stop)")
    Granian("hedge_app:app", address="127.0.0.1", port=args.port, interface="asgi").serve()


if __name__ == "__main__":
    main()
