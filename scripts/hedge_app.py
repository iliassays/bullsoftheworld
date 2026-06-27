"""Hedge — a tiny standalone web app for the daily trading list.

Separate from the Bulls social portal: this is your private morning tool. One page, server-rendered
from the same database + the validated Scheme-3 scan. No build step.

    uv run python scripts/hedge_app.py        # then open http://127.0.0.1:8100
    uv run python scripts/hedge_app.py --port 9000

JSON too: http://127.0.0.1:8100/api/signals
"""

from __future__ import annotations

import argparse

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from hedge_daily import scan
from hedge_forward import read_log, render_ledger, sync
from hedge_history import backtest, render_history

app = FastAPI(title="Hedge")

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
"""


def _shell(active: str, body: str) -> str:
    def tab(href, label):
        return f'<a href="{href}" class="{"on" if active == href else ""}">{label}</a>'

    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Hedge</title>
<style>{_CSS}</style></head><body>
<h1>Hedge <span style="color:#3ddc84">·</span></h1>
<nav>{tab("/", "Today's list")}{tab("/history", "Track record")}</nav>
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


@app.get("/", response_class=HTMLResponse)
async def home(days: int = 10):  # ~2 weeks of recent fires for the morning view
    return _shell("/", _render(await scan(days)))


@app.get("/history", response_class=HTMLResponse)
async def history():
    await sync()  # persist + re-score the ledger, then read it back
    body = render_history(await backtest()) + render_ledger(await read_log())
    return _shell("/history", body)


@app.get("/api/signals")
async def api(days: int = 5):
    return await scan(days)


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
