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
_W, _H = 1200, 630


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


def evening_wrap_card(d: EveningWrapData) -> bytes:
    chg = d.dsex_change
    chg_color = _GREEN if (chg or 0) >= 0 else _RED
    chg_txt = "—" if chg is None else f"{chg:+.2f}%"
    movers_svg = ""
    for i, m in enumerate(d.movers[:3]):
        y = 470 + i * 46
        movers_svg += (
            f'<text x="70" y="{y}" font-size="30" font-family="DejaVu Sans" '
            f'font-weight="bold" fill="{_GOLD}">${_esc(m.code)}</text>'
            f'<text x="330" y="{y}" font-size="30" font-family="DejaVu Sans" '
            f'font-weight="bold" fill="{_GREEN}">{m.change_pct:+.2f}%</text>'
        )
    turnover = "—" if d.turnover_cr is None else f"Tk {_fmt(d.turnover_cr)} cr"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{_W}" height="{_H}" viewBox="0 0 {_W} {_H}">
  <defs><radialGradient id="glow" cx="0.85" cy="0.1" r="0.6">
    <stop offset="0" stop-color="{_GOLD}" stop-opacity="0.16"/><stop offset="1" stop-color="{_GOLD}" stop-opacity="0"/>
  </radialGradient></defs>
  <rect width="{_W}" height="{_H}" fill="{_BG}"/>
  <rect width="{_W}" height="{_H}" fill="url(#glow)"/>
  <image href="{_mark_data_uri()}" x="60" y="48" width="92" height="92"/>
  <text x="168" y="92" font-size="34" font-family="DejaVu Sans" font-weight="bold" fill="#ffffff">Bulls of Dhaka</text>
  <text x="168" y="128" font-size="26" font-family="DejaVu Sans" font-weight="bold" fill="{_GOLD}" letter-spacing="3">EVENING WRAP</text>
  <text x="{_W - 60}" y="92" font-size="26" font-family="DejaVu Sans" fill="#9aa4b2" text-anchor="end">{_esc(d.date_label)}</text>

  <text x="60" y="250" font-size="34" font-family="DejaVu Sans" fill="#9aa4b2">DSEX</text>
  <text x="60" y="320" font-size="76" font-family="DejaVu Sans" font-weight="bold" fill="#ffffff">{_fmt(d.dsex, 2)}</text>
  <text x="600" y="320" font-size="50" font-family="DejaVu Sans" font-weight="bold" fill="{chg_color}">{chg_txt}</text>

  <text x="60" y="392" font-size="30" font-family="DejaVu Sans" fill="{_GREEN}" font-weight="bold">&#9650; {d.advancers} up</text>
  <text x="320" y="392" font-size="30" font-family="DejaVu Sans" fill="{_RED}" font-weight="bold">&#9660; {d.decliners} down</text>
  <text x="610" y="392" font-size="30" font-family="DejaVu Sans" fill="#9aa4b2">&#8226; {d.unchanged} flat</text>
  <text x="{_W - 60}" y="392" font-size="30" font-family="DejaVu Sans" fill="#cbd5e1" text-anchor="end">Turnover {_esc(turnover)}</text>

  <text x="60" y="445" font-size="24" font-family="DejaVu Sans" fill="#9aa4b2" letter-spacing="2">TOP MOVERS</text>
  {movers_svg}

  <text x="60" y="{_H - 36}" font-size="22" font-family="DejaVu Sans" fill="#9aa4b2">bullsofdhaka.com</text>
  <text x="{_W - 60}" y="{_H - 36}" font-size="22" font-family="DejaVu Sans" fill="#6b7280" text-anchor="end">Descriptive data, not advice</text>
</svg>"""
    return render(svg)
