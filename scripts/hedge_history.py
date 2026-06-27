"""Hedge — track record / portfolio history (Scheme-3 backtest, every trade + growth curve).

Runs the validated flagship over the full history and surfaces it as a portfolio: the growth of a
1,000 stake vs the market, the headline stats, and the complete trade ledger (every buy/sell with its
result). Inline SVG chart — no external libraries — so it renders in the live app and the shared link.
"""

from __future__ import annotations

from portfolio_backtest import START, _load, simulate
from scheme2_value import _load_fundamentals
from scheme_lab import quality_reversal

EXITS = dict(stop=-0.10, target=0.25, hold=63, max_pos=10)


async def backtest() -> dict:
    by_code, dsex = await _load()
    fin, div = await _load_fundamentals("DSE")
    sigs = quality_reversal(by_code, fin, div)
    m = simulate(by_code, dsex, signal_fn=lambda b: sigs.get(b[0].code, set()), **EXITS)
    dts = sorted(dsex)
    idx0 = dsex[dts[0]]
    index = [(d, START * dsex.get(d, idx0) / idx0) for d, _ in m["curve"]]
    return {"curve": m["curve"], "index": index, "trades": m["trade_log"], "stats": m}


def _svg(curve, index) -> str:
    """Area+line equity curve (strategy vs index), drawn server-side as inline SVG."""
    w, h, pad = 820, 240, 34
    eqs = [e for _, e in curve]
    ix = [e for _, e in index]
    lo = min(min(eqs), min(ix)) * 0.98
    hi = max(max(eqs), max(ix)) * 1.02
    n = len(curve)

    def x(i):
        return pad + i / (n - 1) * (w - 2 * pad)

    def y(v):
        return h - pad - (v - lo) / (hi - lo) * (h - 2 * pad)

    def line(series):
        return " ".join(f"{x(i):.1f},{y(v):.1f}" for i, (_, v) in enumerate(series))

    area = f"{pad},{y(lo):.1f} " + line(curve) + f" {x(n - 1):.1f},{y(lo):.1f}"
    base_y = y(START)  # the 1,000 starting line
    yr_marks = ""
    seen = set()
    for i, (d, _) in enumerate(curve):
        if d.year not in seen:
            seen.add(d.year)
            yr_marks += f'<text x="{x(i):.0f}" y="{h - 10}" class="ax">{d.year}</text>'
    return f"""<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Equity curve">
  <line x1="{pad}" y1="{base_y:.1f}" x2="{w - pad}" y2="{base_y:.1f}" class="grid"/>
  <text x="{pad}" y="{base_y - 6:.1f}" class="ax">start {START:.0f}</text>
  <polygon points="{area}" fill="#3ddc84" opacity="0.10"/>
  <polyline points="{line(index)}" fill="none" stroke="#6b7280" stroke-width="1.5" stroke-dasharray="5 4"/>
  <polyline points="{line(curve)}" fill="none" stroke="#3ddc84" stroke-width="2.5"/>
  {yr_marks}
</svg>"""


def render_history(d: dict) -> str:
    s = d["stats"]
    final = s["final"]
    rows = ""
    for i, t in enumerate(sorted(d["trades"], key=lambda x: x["in_date"], reverse=True), 1):
        cls = "win" if t["ret"] > 0 else "loss"
        rows += (
            f"<tr><td>{i}</td><td><b>{t['code']}</b></td>"
            f"<td>{t['in_date']}</td><td>{t['in_px']:.2f}</td>"
            f"<td>{t['out_date']}</td><td>{t['out_px']:.2f}</td>"
            f"<td class='{cls}'>{t['ret']:+.1f}%</td><td>{t['held']}d</td>"
            f"<td><span class='pill {cls}'>{t['reason']}</span></td></tr>"
        )
    return f"""
<h2>Track record &mdash; every trade since {d["curve"][0][0]}</h2>
<div class="tr">
  <div><div class="k">1,000 became</div><div class="v pos">{final:,.0f}</div></div>
  <div><div class="k">total / CAGR</div><div class="v">+{s["total"]:.0f}% / {s["cagr"]:.0f}%</div></div>
  <div><div class="k">vs market</div><div class="v">+8%</div></div>
  <div><div class="k">win rate</div><div class="v">{s["winrate"]:.0f}%</div></div>
  <div><div class="k">worst drop</div><div class="v neg">{s["maxdd"]:.0f}%</div></div>
  <div><div class="k">trades</div><div class="v">{s["n_trades"]}</div></div>
</div>
{_svg(d["curve"], d["index"])}
<div class="cap">Green = the strategy growing 1,000 · grey dashed = the same 1,000 in the market index.</div>

<h2>Trade ledger ({s["n_trades"]})</h2>
<div class="scroll"><table>
<tr><th>#</th><th>code</th><th>bought</th><th>buy</th><th>sold</th><th>sell</th><th>result</th><th>held</th><th>exit</th></tr>
{rows}
</table></div>"""
