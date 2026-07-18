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
from hedge_archive import read_daily_snapshots
from hedge_daily import LEGACY_RESEARCH_STATUS, scan_from_snapshot
from hedge_forward import read_log, render_ledger
from hedge_history import read_snapshot, render_history
from risk_calc import MAX_HEAT_PCT, MAX_POSITION_PCT, MAX_POSITIONS, size
from sqlalchemy import case, func, select

from bulls.analytics import STRATEGIES, calculate_agent_performance
from bulls.core.db import bind_tenant_context, get_sessionmaker
from bulls.core.models import (
    AgentLot,
    AgentOpportunity,
    AgentPortfolio,
    AgentTrade,
    PortfolioHolding,
    QuoteSnapshot,
    User,
)
from bulls.market_data.calendar import to_market_tz

app = FastAPI(title="Hedge")

# HTTP only reads persisted batch output and current portfolio state. The short cache avoids repeated
# snapshot reads while still picking up a completed EOD refresh without restarting the web process.
# Per-key locks stop concurrent cold requests from duplicating even that small database read.
_CACHE: dict[object, tuple[float, object]] = {}
_LOCKS: dict[object, asyncio.Lock] = {}
_TTL = 60  # seconds


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
.toolbar{display:flex;gap:12px;align-items:flex-end;justify-content:space-between;flex-wrap:wrap;
  margin:14px 0}
.toolbar form{display:flex;gap:8px;align-items:flex-end}
.toolbar label{font-size:11px;color:#8b909a;text-transform:uppercase;display:block}
.toolbar select{background:#0f1115;border:1px solid #232733;color:#e6e8eb;border-radius:8px;
  padding:8px 10px;font-size:14px;margin-top:4px;cursor:pointer}
.metric-note{font-size:11px;color:#8b909a;margin-top:3px}
.section-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:22px}
.section-head h2{margin:0}
.delta{display:flex;gap:6px;flex-wrap:wrap}
.delta .pill{padding:3px 9px}
.paper-link{color:#3ddc84;text-decoration:none}
.action-link{display:inline-block;color:#3ddc84;text-decoration:none;border:1px solid #2a5a3f;
  border-radius:8px;padding:6px 10px;font-size:12px}
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
<nav>{tab("/", "Quality Reversal")}{tab("/sizing", "Risk / sizing")}{tab("/history", "Legacy backtest")}{tab("/portfolios", "Agent portfolios")}</nav>
{body}
</body></html>"""


def _paper_summary(paper: dict | None) -> str:
    if paper is None:
        return """<div class="card"><div class="why">No dedicated forward paper account exists.
No historical fills will be invented; any future record must begin from an explicitly declared
inception date.</div></div>"""
    return f"""
<div class="tr">
  <div><div class="k">Paper equity</div><div class="v">{_fmt_tk(paper["equity"])}</div></div>
  <div><div class="k">Return</div><div class="v {"pos" if (paper["return_pct"] or 0) >= 0 else "neg"}">{_fmt_pct(paper["return_pct"])}</div></div>
  <div><div class="k">Open positions</div><div class="v">{len(paper["holdings"])} / 10</div></div>
  <div><div class="k">Closed trades</div><div class="v">{paper["closed_trades"]}</div></div>
  <div><div class="k">Blocked setups</div><div class="v">{paper["opportunities_open"]}</div></div>
</div>
<div class="cap">Forward-only account: previous-session archived signals, next-session delayed
quote fills, 0.4% brokerage each side, DSE settlement, -10% stop, +25% target, 63-session time exit.
Entries blocked at the upper circuit are not treated as fills.
<a class="paper-link" href="/portfolios?p={paper["handle"]}">Open holdings, missed opportunities and trade audit →</a></div>"""


def _render(
    d: dict,
    *,
    archive: list,
    selected_date: str,
    evidence_hash: str | None,
    computed_at: dt.datetime | None,
    paper: dict | None,
) -> str:
    if not d.get("ready", True):
        return f"""
<div class="sub">Daily list · EOD {d["as_of"]} · delayed data · for your own use, not advice</div>
<h2>Daily scan is preparing</h2>
<div class="card"><div class="why">The scheduled EOD refresh has not published the buy-list snapshot
yet. This page will not run the full-market scan inside your browser request. Try again after the
next refresh.</div></div>"""
    selected_index = next(
        (index for index, row in enumerate(archive) if row.as_of_date.isoformat() == selected_date),
        0,
    )
    archive_options = "".join(
        f'<option value="{row.as_of_date}" {"selected" if row.as_of_date.isoformat() == selected_date else ""}>'
        f"{row.as_of_date}{' · latest' if index == 0 else ''}</option>"
        for index, row in enumerate(archive)
    )
    buys = (
        "".join(
            f"""<div class="card"><div class="top"><span class="tk">{x["code"]}</span>
        <span class="tag">{x["sector"]}</span></div>
        <div class="lvl">
          <div><div class="k">signal close</div><div class="v">{x["price"]}</div></div>
          <div><div class="k">stop</div><div class="v neg">{x["stop"]}</div></div>
          <div><div class="k">target</div><div class="v pos">{x["target"]}</div></div>
          <div><div class="k">P/E · ROE</div><div class="v">{x["pe"]} · {x["roe"]}%</div></div>
        </div>
        <div class="why">washed-out {x["below_high"]}% off its high · cheap + profitable ·
        five-session breakout confirmed at this EOD · conviction {x["score"]}/100</div>
        </div>"""
            for x in d["fired"]
        )
        or '<div class="empty">No new Quality Reversal signal was confirmed in this session.</div>'
    )

    watch = (
        "".join(
            f"<tr><td><b>{x['code']}</b></td><td>{x['price']}</td><td>{x['pe']}</td>"
            f"<td>{x['roe']}%</td><td>{x['below_high']}%</td><td>{x['sector']}</td></tr>"
            for x in d["watch"]
        )
        or '<tr><td colspan="6" class="empty">Nothing set up right now.</td></tr>'
    )
    active = (
        "".join(
            f"<tr><td>{x['signal_date']}</td><td><b>{x['code']}</b></td>"
            f"<td class='num'>{x['entry']:.2f}</td><td class='num'>{x['price']:.2f}</td>"
            f"<td class='num {'pos' if x['return_pct'] >= 0 else 'neg'}'>{x['return_pct']:+.1f}%</td>"
            f"<td class='num neg'>{x['stop']:.2f}</td><td class='num pos'>{x['target']:.2f}</td></tr>"
            for x in d.get("active", [])
        )
        or '<tr><td colspan="7" class="empty">No historical signal episode remains open.</td></tr>'
    )
    changes = d.get("changes", {})
    added = ", ".join(changes.get("added", [])) or "none"
    removed = ", ".join(changes.get("removed", [])) or "none"
    archive_note = (
        f"Archive session {selected_index + 1} of {len(archive)}"
        if archive
        else "Archive begins with the first publication"
    )

    return f"""
<div class="toolbar">
  <div>
    <h1 style="font-size:20px">Quality Reversal Monitor</h1>
    <div class="sub">Published after each DSE EOD refresh, normally around 20:20 BDT · not intraday</div>
  </div>
  <form method="get" action="/">
    <div><label>Published session</label><select name="date" onchange="this.form.submit()">
      {archive_options or f'<option value="{selected_date}">{selected_date}</option>'}
    </select></div>
  </form>
</div>
<div class="cap">Viewing <b>{d["as_of"]}</b> · published
{computed_at.strftime("%Y-%m-%d %H:%M UTC") if computed_at else "offline"} ·
evidence {evidence_hash[:12] if evidence_hash else "pending"} · {archive_note}</div>
<div class="tr">
  <div><div class="k">New this EOD</div><div class="v">{len(d["fired"])}</div><div class="metric-note">eligible next session</div></div>
  <div><div class="k">Signals still open</div><div class="v">{len(d.get("active", []))}</div><div class="metric-note">outcome tracker, not holdings</div></div>
  <div><div class="k">Waiting for trigger</div><div class="v">{len(d["watch"])}</div><div class="metric-note">setup only</div></div>
  <div><div class="k">Removed vs prior</div><div class="v">{len(changes.get("removed", []))}</div><div class="metric-note">no longer monitored</div></div>
</div>
<div class="card"><div class="why"><b>Frozen legacy research monitor.</b> Performance is not copied
into this daily screen. The <a class="paper-link" href="/history">Legacy backtest</a> page reads the
latest dynamically computed diagnostic and states its same-close, no-slippage limitations. It is
not an Atlas track record, a paper execution record, or evidence that this session's names are
profitable.</div></div>
<div class="section-head"><h2>New signals ({len(d["fired"])})</h2>
<a class="action-link" href="/sizing?date={selected_date}">Size this session</a></div>
{buys}
<div class="section-head"><h2>Open signal episodes ({len(d.get("active", []))})</h2>
<span class="pill">target / stop / 63 sessions</span></div>
<div class="scroll"><table><tr><th>signal date</th><th>code</th><th class="num">signal close</th>
<th class="num">current</th><th class="num">since signal</th><th class="num">stop</th>
<th class="num">target</th></tr>{active}</table></div>
<div class="section-head"><h2>Watchlist ({len(d["watch"])})</h2>
<span class="pill">setup waiting for breakout</span></div>
<table><tr><th>code</th><th>price</th><th>P/E</th><th>ROE</th><th>off high</th><th>sector</th></tr>
{watch}</table>
<div class="section-head"><h2>Session changes</h2><span class="pill">vs prior archived session</span></div>
<div class="card"><div class="why"><b class="pos">Added:</b> {added}<br>
<b class="neg">Removed:</b> {removed}<br>
“Added” means newly present in the monitor, not necessarily a buy signal. “Removed” means the
name is no longer new, active, or waiting in the current setup.</div></div>
<div class="section-head"><h2>Exact-strategy paper account</h2>
<span class="pill win">forward only</span></div>
{_paper_summary(paper)}
<div class="foot">Daily publications are append-only and fingerprinted. The archive begins at this
feature's deployment; earlier day-by-day screens are not fabricated from hindsight. Risk/Sizing
uses only the selected session's new signals. The paper engine checks observed delayed quotes every
15 minutes during the following DSE session.</div>"""


def render_sizing(d: dict, capital: float, risk: float, held: int) -> str:
    if not d.get("ready", True):
        return f"""
<div class="sub">Risk / sizing · EOD {d["as_of"]} · delayed data</div>
<h2>Position sizing is preparing</h2>
<div class="card"><div class="why">Sizing uses the scheduled EOD buy-list snapshot, which has not
completed yet. The web request deliberately does not run a full-universe scan. Try again after the
next refresh.</div></div>"""
    r = size(capital, risk, d["fired"], held=held)
    rows, invested, heat, reserved = r["rows"], r["invested"], r["heat"], r["reserved"]
    pct = lambda x: x / capital * 100 if capital else 0  # noqa: E731
    body = "".join(
        f"<tr><td><b>{x['code']}</b></td><td class='num'>{x['score'] or 0}</td>"
        f"<td class='num'>{x['entry']:.1f}</td>"
        f"<td class='num neg'>{x['stop']:.1f}</td><td class='num pos'>{x['target']:.1f}</td>"
        f"<td class='num'>{x['shares']:,}</td><td class='num'>{x['invested']:,.0f}</td>"
        f"<td class='num'>{x['risk']:,.0f}</td><td class='num pos'>{x['reward']:,.0f}</td></tr>"
        for x in rows
    ) or (
        f'<tr><td colspan="9" class="empty">No free slots — you already hold {held} of '
        f"{MAX_POSITIONS}. Wait for an exit.</td></tr>"
        if d["fired"]
        else '<tr><td colspan="9" class="empty">No new signal was confirmed for this EOD session.</td></tr>'
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
<div class="sub">Sizing this session's confirmed signals · holding {held}, {r["free"]} of {MAX_POSITIONS} slots free · fund {len(rows)}, waitlist {len(r["waitlist"])} · EOD {d["as_of"]}</div>
<form class="sz" method="get" action="/sizing">
  <input type="hidden" name="date" value="{d["as_of"]}">
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
<tr><th>code</th><th class="num">conv</th><th class="num">signal px</th><th class="num">stop</th><th class="num">target</th>
<th class="num">shares</th><th class="num">invest ৳</th><th class="num">risk ৳</th><th class="num">reward ৳</th></tr>
{body}</table>
{wait}
<div class="cap">"At risk" = your total loss if every open trade (held + new) stops out at once. Each name is
sized so a stop-out costs ~{risk:g}% of capital; capped at {MAX_POSITION_PCT:.0f}% per name and {MAX_HEAT_PCT:.0f}% total.
You never hold more than {MAX_POSITIONS} — extra signals wait for a slot to free, which is why a fresh
batch can never demand money you don't have. "conv" = the strategy's conviction rank (fund the top first).</div>
<div class="cap">This is a planning calculator using the EOD signal close. The forward paper account
records its own next-session observed fill price; it does not claim execution at this reference price.</div>
<h2>How many names? (risk % sets it automatically)</h2>
<table>
<tr><th class="num">risk/trade</th><th class="num">position size</th><th class="num">max names</th><th class="num">portfolio max loss</th></tr>
{ref}</table>
<div class="foot">Lower the risk % for smaller positions across more names (more diversification); raise it
for fewer, bigger ones. The DSE ~10% circuit breaker makes the -10% stop reliable — over the 2-year
backtest no trade lost more than the stop, so "{risk:g}% at risk" holds up. Delayed EOD data · your own use, not advice.</div>"""


async def _agent_book(handles: set[str] | None = None) -> list[dict]:
    """All agent portfolios from six bulk queries, priced against the latest DSE quotes."""
    tenant_id, market = "bullsofdhaka", "DSE"
    today = to_market_tz(dt.datetime.now(dt.UTC), market=market).date()
    out: list[dict] = []
    async with get_sessionmaker()() as session:
        await bind_tenant_context(session, tenant_id)
        stmt = (
            select(AgentPortfolio, User)
            .join(User, User.id == AgentPortfolio.user_id)
            .where(
                AgentPortfolio.market == market,
                User.tenant_id == tenant_id,
            )
        )
        if handles:
            stmt = stmt.where(User.handle.in_(handles))
        rows = (await session.execute(stmt)).all()
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
        opportunity_counts: dict[int, dict[str, int]] = defaultdict(lambda: {"open": 0, "total": 0})
        for user_id, status, count in (
            await session.execute(
                select(
                    AgentOpportunity.user_id,
                    AgentOpportunity.status,
                    func.count(AgentOpportunity.id),
                )
                .where(
                    AgentOpportunity.tenant_id == tenant_id,
                    AgentOpportunity.market == market,
                    AgentOpportunity.user_id.in_(user_ids),
                )
                .group_by(AgentOpportunity.user_id, AgentOpportunity.status)
            )
        ).all():
            opportunity_counts[user_id]["total"] += count
            if status == "open":
                opportunity_counts[user_id]["open"] = count

        ranked_opportunity_ids = (
            select(
                AgentOpportunity.id,
                func.row_number()
                .over(
                    partition_by=AgentOpportunity.user_id,
                    order_by=(
                        case((AgentOpportunity.status == "open", 0), else_=1),
                        AgentOpportunity.id.desc(),
                    ),
                )
                .label("row_number"),
            )
            .where(
                AgentOpportunity.tenant_id == tenant_id,
                AgentOpportunity.market == market,
                AgentOpportunity.user_id.in_(user_ids),
            )
            .subquery()
        )
        opportunities = (
            await session.scalars(
                select(AgentOpportunity)
                .join(
                    ranked_opportunity_ids,
                    ranked_opportunity_ids.c.id == AgentOpportunity.id,
                )
                .where(ranked_opportunity_ids.c.row_number <= 50)
                .order_by(AgentOpportunity.user_id, AgentOpportunity.id.desc())
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
        opportunities_by_user: dict[int, list] = defaultdict(list)
        for holding in holdings:
            holdings_by_user[holding.user_id].append(holding)
        for lot in lots:
            lots_by_user[lot.user_id].append(lot)
        for trade in all_trades:
            trades_by_user[trade.user_id].append(trade)
        for opportunity in opportunities:
            opportunities_by_user[opportunity.user_id].append(opportunity)

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
            opportunity_rows = []
            for opportunity in opportunities_by_user[agent.user_id]:
                first_price = opportunity.first_price
                opportunity_rows.append(
                    {
                        "code": opportunity.code,
                        "status": opportunity.status,
                        "block_reason": opportunity.last_block_reason,
                        "first_seen_at": opportunity.first_seen_at,
                        "last_seen_at": opportunity.last_seen_at,
                        "first_price": first_price,
                        "last_price": opportunity.last_price,
                        "return_pct": (opportunity.last_price / first_price - 1) * 100,
                        "best_return_pct": (opportunity.best_price / first_price - 1) * 100,
                        "worst_return_pct": (opportunity.worst_price / first_price - 1) * 100,
                        "first_rank": opportunity.first_rank,
                        "best_rank": opportunity.best_rank,
                        "last_rank": opportunity.last_rank,
                        "required_cash": opportunity.required_cash,
                        "available_cash": opportunity.last_available_cash,
                        "pending_cash": opportunity.last_pending_cash,
                        "free_slots": opportunity.last_free_slots,
                        "blocked_ticks": opportunity.blocked_ticks,
                        "signal_reason": opportunity.signal_reason,
                    }
                )

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
                    "strategy": agent.strategy,
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
                    "opportunities_open": opportunity_counts[agent.user_id]["open"],
                    "opportunities_total": opportunity_counts[agent.user_id]["total"],
                    "opportunities": opportunity_rows,
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
                f"<td class='num'>{a['opportunities_open']}</td>"
                f"<td class='num'>{_fmt_pct(a['return_pct'])}</td></tr>"
                for a in book
            )
            or '<tr><td colspan="8" class="empty">No agent portfolios seeded.</td></tr>'
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
<th class="num">cash ৳</th><th class="num">settling ৳</th><th class="num">positions</th>
<th class="num">blocked now</th><th class="num">return</th></tr>
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
    opportunity_status = {
        "open": ("watch", "still blocked"),
        "entered": ("win", "entered later"),
        "expired": ("", "setup expired"),
    }
    opportunity_reason = {
        "no_cash": "not enough settled cash",
        "no_slot": "all position slots used",
        "order_too_small": "budget below executable order",
    }
    opportunity_rows = (
        "".join(
            f"<tr><td>{op['first_seen_at'].strftime('%Y-%m-%d %H:%M')}</td>"
            f"<td><b>{op['code']}</b></td>"
            f"<td><span class='pill {opportunity_status[op['status']][0]}'>"
            f"{opportunity_status[op['status']][1]}</span></td>"
            f"<td>{opportunity_reason[op['block_reason']]}</td>"
            f"<td class='num'>{op['best_rank']}</td>"
            f"<td class='num'>{op['first_price']:.2f}</td>"
            f"<td class='num {'pos' if op['return_pct'] >= 0 else 'neg'}'>"
            f"{op['return_pct']:+.1f}%</td>"
            f"<td class='num pos'>{op['best_return_pct']:+.1f}%</td>"
            f"<td class='num neg'>{op['worst_return_pct']:+.1f}%</td>"
            f"<td class='num'>{op['available_cash']:,.0f} / {op['required_cash']:,.0f}</td>"
            f"<td class='num'>{op['free_slots']}</td></tr>"
            for op in chosen["opportunities"]
        )
        or '<tr><td colspan="11" class="empty">No capital-constrained setups recorded yet.</td></tr>'
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
  <div><div class="k">Blocked now</div><div class="v">{chosen["opportunities_open"]}</div></div>
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
<h2>Capital-constrained opportunities ({chosen["opportunities_total"]} episodes)</h2>
<div class="cap">A setup appears here only when the strategy qualified but the account could not
buy it. The setup comes from EOD analytics; the price path uses observed 15-minute delayed quotes.
Returns are counterfactual observations, not portfolio P&amp;L or hypothetical fills. Recording starts
from this feature's deployment; older discarded candidates cannot be reconstructed honestly.</div>
<div class="scroll"><table>
<tr><th>first seen</th><th>code</th><th>outcome</th><th>blocked by</th><th class="num">best rank</th>
<th class="num">missed px</th><th class="num">since</th><th class="num">best</th>
<th class="num">worst</th><th class="num">cash / needed</th><th class="num">slots</th></tr>
{opportunity_rows}
</table></div>
<h2>Trade log ({len(chosen["trades"])})</h2>
<div class="scroll"><table>
<tr><th>date</th><th>side</th><th>code</th><th class="num">qty</th><th class="num">price</th>
<th class="num">fee</th><th>settles</th><th>reason</th></tr>
{trades}</table></div>
<div class="foot">"Sellable" counts only shares past T+2 settlement — the engine cannot sell the
rest yet, whatever the price does. Every fill is at the delayed last-traded price + 0.4% brokerage.
Paper trading · not advice.</div>"""


async def _archive_view(selected_date: str = ""):
    """Selected immutable publication plus the bounded archive index."""
    archive = await _cached("daily-archive", lambda: read_daily_snapshots(limit=90))
    if archive:
        chosen = next(
            (row for row in archive if row.as_of_date.isoformat() == selected_date),
            archive[0],
        )
        return scan_from_snapshot(chosen.payload), archive, chosen

    snapshot = await read_snapshot()
    daily_scan = snapshot.payload.get("daily_scan") if snapshot else None
    if daily_scan:
        return scan_from_snapshot(daily_scan), [], None
    return (
        {
            "as_of": snapshot.as_of_date.isoformat() if snapshot else "not available",
            "fired": [],
            "watch": [],
            "active": [],
            "changes": {},
            "research_status": LEGACY_RESEARCH_STATUS,
            "ready": False,
        },
        [],
        None,
    )


async def _history_body() -> str:
    snapshot = await read_snapshot()
    if snapshot is None:
        return """<h2>Legacy diagnostic is unavailable</h2>
<div class="card"><div class="why">The persisted batch snapshot has not completed yet. This page
never runs the multi-year simulation inside a browser request and will not substitute a hard-coded
performance claim.</div></div>"""
    return render_history(
        snapshot.payload,
        computed_at=snapshot.computed_at,
        as_of_date=snapshot.as_of_date,
    ) + render_ledger(await read_log())


@app.get("/", response_class=HTMLResponse)
async def home(date: str = ""):
    (d, archive, publication), paper_book = await asyncio.gather(
        _archive_view(date),
        _agent_book({"QualityReversalPortfolio"}),
    )
    selected_date = publication.as_of_date.isoformat() if publication else d["as_of"]
    return _shell(
        "/",
        _render(
            d,
            archive=archive,
            selected_date=selected_date,
            evidence_hash=publication.content_hash if publication else None,
            computed_at=publication.computed_at if publication else None,
            paper=paper_book[0] if paper_book else None,
        ),
    )


@app.get("/sizing", response_class=HTMLResponse)
async def sizing(capital: float = 200_000, risk: float = 1.0, held: int = 0, date: str = ""):
    risk = min(max(risk, 0.25), 3.0)  # keep the knob in a sane band
    held = min(max(held, 0), MAX_POSITIONS)
    d, _archive, _publication = await _archive_view(date)
    return _shell("/sizing", render_sizing(d, capital, risk, held))


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
async def api(date: str = ""):
    d, _archive, _publication = await _archive_view(date)
    return d


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
