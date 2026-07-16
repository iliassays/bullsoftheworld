"""Hedge forward log — a persisted, self-scoring ledger of every signal.

Writes each Scheme-3 signal to its own table (hedge_log), then scores it against later prices
(target / stop / 3-month time exit). Run it daily (or cron it): new signals get logged, open ones get
re-scored as fresh bars arrive. On first run it backfills the full signal history so the record is
useful immediately; from then on it grows forward. Isolated table — does not touch the portal schema.

    uv run python scripts/hedge_forward.py        # sync + print status (run daily)
"""

from __future__ import annotations

import asyncio

from hedge_history import STRATEGY_KEY
from portfolio_backtest import WARMUP, _load
from scheme2_value import _load_fundamentals
from scheme_lab import quality_reversal
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bulls.core.db import bind_tenant_context, get_sessionmaker
from bulls.core.models import HedgeSignal

STOP, TARGET, HOLD = -0.10, 0.25, 63


def _score(bars, i):
    """Track one signal entered at bar i to its target / stop / time exit, or 'open'."""
    entry = bars[i].close
    stop_px, tgt_px = entry * (1 + STOP), entry * (1 + TARGET)
    for j in range(i + 1, len(bars)):
        b = bars[j]
        if b.low <= stop_px:
            return "stop", b.date, round(stop_px, 2), round((stop_px / entry - 1) * 100, 1)
        if b.high >= tgt_px:
            return "target", b.date, round(tgt_px, 2), round((tgt_px / entry - 1) * 100, 1)
        if j - i >= HOLD:
            return "time", b.date, round(b.close, 2), round((b.close / entry - 1) * 100, 1)
    return "open", None, None, None  # still running


def build_rows(by_code, sigs) -> list[dict]:
    """Score every signal using an already-loaded dataset."""
    rows = []
    for code, dates in sigs.items():
        bars = by_code[code]
        idx = {b.date: k for k, b in enumerate(bars)}
        for sd in dates:
            i = idx.get(sd)
            if i is None or i < WARMUP:
                continue
            entry = bars[i].close
            status, ed, ex, res = _score(bars, i)
            rows.append(
                {
                    "tenant_id": "bullsofdhaka",
                    "market": "DSE",
                    "strategy": STRATEGY_KEY,
                    "code": code,
                    "signal_date": sd,
                    "entry": round(entry, 2),
                    "stop": round(entry * (1 + STOP), 2),
                    "target": round(entry * (1 + TARGET), 2),
                    "status": status,
                    "exit_date": ed,
                    "exit_px": ex,
                    "result_pct": res,
                }
            )
    return rows


async def replace_rows(
    session: AsyncSession,
    rows: list[dict],
    *,
    tenant_id: str = "bullsofdhaka",
    market: str = "DSE",
) -> None:
    """Atomically replace one strategy ledger so deleted/corrected historical signals disappear."""
    await session.execute(
        delete(HedgeSignal).where(
            HedgeSignal.tenant_id == tenant_id,
            HedgeSignal.market == market,
            HedgeSignal.strategy == STRATEGY_KEY,
        )
    )
    if rows:
        session.add_all(
            [
                HedgeSignal(
                    **{
                        **row,
                        "tenant_id": tenant_id,
                        "market": market,
                        "strategy": STRATEGY_KEY,
                    }
                )
                for row in rows
            ]
        )


async def sync() -> dict:
    """Manual compatibility entry point. Scheduled refreshes use hedge_refresh.py to load once."""
    by_code, _ = await _load()
    fin, div = await _load_fundamentals("DSE")
    sigs = quality_reversal(by_code, fin, div)
    rows = build_rows(by_code, sigs)
    sm = get_sessionmaker()
    async with sm() as s:
        await bind_tenant_context(s, "bullsofdhaka")
        await replace_rows(s, rows)
        await s.commit()
    return {"logged": len(rows), "open": sum(1 for r in rows if r["status"] == "open")}


async def read_log() -> dict:
    """Read the ledger back: summary stats + all rows (newest first)."""
    sm = get_sessionmaker()
    async with sm() as s:
        await bind_tenant_context(s, "bullsofdhaka")
        res = (
            await s.scalars(
                select(HedgeSignal)
                .where(
                    HedgeSignal.tenant_id == "bullsofdhaka",
                    HedgeSignal.market == "DSE",
                    HedgeSignal.strategy == STRATEGY_KEY,
                )
                .order_by(HedgeSignal.signal_date.desc())
            )
        ).all()
    rows = [
        {
            "code": r.code,
            "signal_date": r.signal_date,
            "entry": r.entry,
            "stop": r.stop,
            "target": r.target,
            "status": r.status,
            "exit_date": r.exit_date,
            "exit_px": r.exit_px,
            "result_pct": r.result_pct,
            "created_at": r.created_at,
        }
        for r in res
    ]
    closed = [r for r in rows if r["status"] != "open"]
    wins = [r for r in closed if (r["result_pct"] or 0) > 0]
    return {
        "rows": rows,
        "total": len(rows),
        "open": sum(1 for r in rows if r["status"] == "open"),
        "closed": len(closed),
        "win_rate": round(len(wins) / len(closed) * 100) if closed else 0,
        "avg": round(sum(r["result_pct"] for r in closed) / len(closed), 1) if closed else 0,
        "since": min((r["signal_date"] for r in rows), default=None),
    }


def render_ledger(log: dict) -> str:
    """The persisted signal ledger as an HTML section (summary cards + scrollable table)."""
    rows = ""
    for r in log["rows"]:
        res = r["result_pct"]
        cls = "win" if (res or 0) > 0 else ("loss" if res is not None else "")
        pill = {"target": "win", "stop": "loss", "time": "", "open": ""}[r["status"]]
        rows += (
            f"<tr><td>{r['signal_date']}</td><td><b>{r['code']}</b></td>"
            f"<td>{r['entry']:.2f}</td><td><span class='pill {pill}'>{r['status']}</span></td>"
            f"<td>{r['exit_date'] or '—'}</td>"
            f"<td class='{cls}'>{(f'{res:+.1f}%') if res is not None else 'running'}</td></tr>"
        )
    return f"""
<h2>Signal ledger &mdash; persisted &amp; growing (since {log["since"]})</h2>
<div class="tr">
  <div><div class="k">signals logged</div><div class="v">{log["total"]}</div></div>
  <div><div class="k">closed</div><div class="v">{log["closed"]}</div></div>
  <div><div class="k">win rate</div><div class="v pos">{log["win_rate"]}%</div></div>
  <div><div class="k">avg result</div><div class="v pos">+{log["avg"]}%</div></div>
  <div><div class="k">open now</div><div class="v">{log["open"]}</div></div>
</div>
<div class="cap">Every Scheme-3 signal, persisted and re-scored daily. Backfilled at launch, grows
forward from here — new picks log automatically, open ones close as they hit target/stop/time.</div>
<div class="scroll"><table>
<tr><th>signal date</th><th>code</th><th>entry</th><th>status</th><th>exit date</th><th>result</th></tr>
{rows}
</table></div>"""


async def _run():
    print("Syncing Hedge forward log...")
    st = await sync()
    log = await read_log()
    print(f"  logged {st['logged']} signals ({st['open']} open) · since {log['since']}")
    print(f"  closed {log['closed']} · win-rate {log['win_rate']}% · avg result {log['avg']:+}%")


if __name__ == "__main__":
    asyncio.run(_run())
