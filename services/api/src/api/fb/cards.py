"""Branded shareable card images for Facebook posts.

Cards are built as SVG (brand template + data) and rasterised to PNG with `rsvg-convert`
(librsvg). One renderer, one template per post pillar — add a pillar by adding a `*_card()`
builder. Card text is English/numeric (universal); the bilingual prose lives in the post caption.
"""

from __future__ import annotations

import base64
import subprocess
from dataclasses import dataclass
from pathlib import Path

_MARK = Path(__file__).parent / "assets" / "mark.png"
_GOLD = "#f5b82e"
_GREEN = "#2ecc71"
_RED = "#ef5350"
_BG = "#0b0f14"
_GREY = "#9aa4b2"
_W, _H = 1200, 725


class CardError(RuntimeError):
    pass


def _mark_data_uri() -> str:
    b64 = base64.b64encode(_MARK.read_bytes()).decode()
    return f"data:image/png;base64,{b64}"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(svg: str, w: int = _W, h: int = _H) -> bytes:
    """Rasterise an SVG string to PNG bytes via rsvg-convert."""
    try:
        proc = subprocess.run(
            ["rsvg-convert", "-w", str(w), "-h", str(h), "-b", _BG],
            input=svg.encode(),
            capture_output=True,
            timeout=20,
        )
    except FileNotFoundError as e:
        raise CardError("rsvg-convert not installed") from e
    if proc.returncode != 0:
        raise CardError(f"rsvg-convert failed: {proc.stderr.decode()[:200]}")
    return proc.stdout


@dataclass
class Mover:
    code: str
    change_pct: float


@dataclass
class EveningWrapData:
    date_label: str  # e.g. "28 Jun 2026"
    dsex: float | None
    dsex_change: float | None  # %
    advancers: int
    decliners: int
    unchanged: int
    turnover_cr: float | None  # BDT crore
    movers: list[Mover]  # top gainers


def _fmt(n: float | None, dp: int = 0) -> str:
    return "—" if n is None else f"{n:,.{dp}f}"


def _stat_cell(cx: float, head: str, head_color: str, value: str, label: str) -> str:
    return (
        f'<text x="{cx}" y="408" font-size="27" font-family="DejaVu Sans" text-anchor="middle">'
        f'<tspan fill="{head_color}" font-weight="bold">{head}</tspan>'
        f'<tspan fill="#ffffff" font-weight="bold" dx="9">{value}</tspan>'
        f'<tspan fill="{_GREY}" font-size="23" dx="8">{label}</tspan></text>'
    )


def _mover_row(m: Mover, idx: int, badge_x: int, code_x: int, pct_x: int, y: int) -> str:
    return (
        f'<rect x="{badge_x}" y="{y - 22}" width="30" height="30" rx="7" fill="#1c232d"/>'
        f'<text x="{badge_x + 15}" y="{y}" font-size="18" font-family="DejaVu Sans" '
        f'fill="{_GREY}" text-anchor="middle">{idx}</text>'
        f'<text x="{code_x}" y="{y}" font-size="27" font-family="DejaVu Sans" '
        f'font-weight="bold" fill="{_GOLD}">${_esc(m.code)}</text>'
        f'<text x="{pct_x}" y="{y}" font-size="27" font-family="DejaVu Sans" '
        f'font-weight="bold" fill="{_GREEN}" text-anchor="end">{m.change_pct:+.2f}%</text>'
    )


def evening_wrap_card(d: EveningWrapData) -> bytes:
    chg = d.dsex_change
    chg_color = _GREEN if (chg or 0) >= 0 else _RED
    chg_txt = "—" if chg is None else f"{chg:+.2f}%"
    turnover = "—" if d.turnover_cr is None else f"Tk {_fmt(d.turnover_cr)} cr"

    # Top movers — two-column grid (up to 6)
    rows = ""
    cols = [(70, 110, 560), (620, 660, 1130)]  # (badge_x, code_x, pct_x) per column
    ys = [556, 600, 644]
    for i, m in enumerate(d.movers[:6]):
        badge_x, code_x, pct_x = cols[i // 3]
        rows += _mover_row(m, i + 1, badge_x, code_x, pct_x, ys[i % 3])

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{_W}" height="{_H}" viewBox="0 0 {_W} {_H}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#11161d"/><stop offset="1" stop-color="#080b0f"/></linearGradient>
    <radialGradient id="glow" cx="0.82" cy="0.12" r="0.55"><stop offset="0" stop-color="{_GOLD}" stop-opacity="0.18"/><stop offset="1" stop-color="{_GOLD}" stop-opacity="0"/></radialGradient>
    <linearGradient id="goldline" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{_GOLD}" stop-opacity="0"/><stop offset="1" stop-color="{_GOLD}" stop-opacity="0.9"/></linearGradient>
  </defs>
  <rect width="{_W}" height="{_H}" fill="url(#bg)"/>
  <rect width="{_W}" height="{_H}" fill="url(#glow)"/>

  <!-- header -->
  <image href="{_mark_data_uri()}" x="50" y="40" width="86" height="86"/>
  <text x="150" y="82" font-size="40" font-family="DejaVu Sans" font-weight="bold" fill="#ffffff">Bulls of Dhaka</text>
  <text x="152" y="118" font-size="23" font-family="DejaVu Sans" font-weight="bold" fill="{_GOLD}" letter-spacing="6">EVENING WRAP</text>
  <text x="1150" y="78" font-size="27" font-family="DejaVu Sans" fill="{_GREY}" text-anchor="end">{_esc(d.date_label)}</text>
  <rect x="960" y="92" width="190" height="3" rx="1.5" fill="url(#goldline)"/>

  <!-- DSEX -->
  <text x="54" y="200" font-size="30" font-family="DejaVu Sans" fill="{_GREY}" letter-spacing="4">DSEX</text>
  <text x="50" y="300" font-size="94" font-family="DejaVu Sans" font-weight="bold" fill="#ffffff">{_fmt(d.dsex, 2)}</text>
  <line x1="700" y1="238" x2="700" y2="300" stroke="{_GOLD}" stroke-opacity="0.45" stroke-width="3"/>
  <text x="740" y="296" font-size="66" font-family="DejaVu Sans" font-weight="bold" fill="{chg_color}">{chg_txt}</text>
  <rect x="50" y="330" width="560" height="3" rx="1.5" fill="url(#goldline)" opacity="0.5"/>

  <!-- stat row -->
  <rect x="50" y="366" width="1100" height="70" rx="14" fill="#10151c" stroke="#ffffff" stroke-opacity="0.10"/>
  <line x1="325" y1="384" x2="325" y2="418" stroke="#ffffff" stroke-opacity="0.10"/>
  <line x1="600" y1="384" x2="600" y2="418" stroke="#ffffff" stroke-opacity="0.10"/>
  <line x1="875" y1="384" x2="875" y2="418" stroke="#ffffff" stroke-opacity="0.10"/>
  {_stat_cell(187, "&#9650;", _GREEN, str(d.advancers), "up")}
  {_stat_cell(462, "&#9660;", _RED, str(d.decliners), "down")}
  {_stat_cell(737, "&#8226;", _GREY, str(d.unchanged), "flat")}
  <text x="1012" y="408" font-size="25" font-family="DejaVu Sans" text-anchor="middle"><tspan fill="{_GREY}" font-size="23">Turnover</tspan><tspan fill="#ffffff" font-weight="bold" dx="9">{_esc(turnover)}</tspan></text>

  <!-- top movers -->
  <rect x="50" y="476" width="7" height="28" rx="2" fill="{_GOLD}"/>
  <text x="72" y="499" font-size="26" font-family="DejaVu Sans" font-weight="bold" fill="{_GOLD}" letter-spacing="4">TOP MOVERS</text>
  <rect x="50" y="520" width="1100" height="150" rx="16" fill="#10151c" stroke="#ffffff" stroke-opacity="0.10"/>
  <line x1="600" y1="540" x2="600" y2="650" stroke="#ffffff" stroke-opacity="0.10"/>
  <line x1="80" y1="578" x2="560" y2="578" stroke="#ffffff" stroke-opacity="0.07"/>
  <line x1="80" y1="622" x2="560" y2="622" stroke="#ffffff" stroke-opacity="0.07"/>
  <line x1="640" y1="578" x2="1120" y2="578" stroke="#ffffff" stroke-opacity="0.07"/>
  <line x1="640" y1="622" x2="1120" y2="622" stroke="#ffffff" stroke-opacity="0.07"/>
  {rows}

  <!-- footer -->
  <text x="54" y="{_H - 30}" font-size="22" font-family="DejaVu Sans" fill="{_GREY}">bullsofdhaka.com</text>
  <text x="{_W - 50}" y="{_H - 30}" font-size="21" font-family="DejaVu Sans" fill="#6b7280" text-anchor="end">Informational data, not investment advice</text>
</svg>"""
    return render(svg)
