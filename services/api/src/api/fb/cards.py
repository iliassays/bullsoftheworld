"""Branded shareable card images for Facebook posts.

Cards are a strict fixed-grid SVG template (1600x900) rasterised to PNG with `rsvg-convert`.
Fonts (Inter, 4 weights) and the logo are embedded so a card renders identically anywhere.
Icons are drawn as vector (emoji don't render in librsvg). One builder per pillar.
Card text is English/numeric; the bilingual prose lives in the post caption.
"""

from __future__ import annotations

import base64
import functools
import subprocess
from dataclasses import dataclass
from pathlib import Path

_ASSETS = Path(__file__).parent / "assets"
_MARK = _ASSETS / "mark.png"
_FONT = "Inter"
_GOLD = "#f5b82e"
_GREEN = "#2ecc71"
_RED = "#ef5350"
_WHITE = "#f5f7fa"
_GREY = "#9aa4b2"
_BG = "#070b12"
_PANEL = "#070f1b"  # rendered at 0.8 opacity
_BORDER = _GOLD  # at 0.25 opacity — one border style everywhere
_SEP = "#ffffff"  # at 0.08 opacity — one separator style everywhere
_W, _H = 1600, 900


class CardError(RuntimeError):
    pass


def _b64(p: Path) -> str:
    return base64.b64encode(p.read_bytes()).decode()


def _mark_data_uri() -> str:
    return f"data:image/png;base64,{_b64(_MARK)}"


@functools.cache
def _font_face() -> str:
    """Embed Inter (400/500/700/800) so weight hierarchy renders identically anywhere."""
    faces = ""
    for weight, fname in (
        (400, "Inter-Regular.ttf"),
        (500, "Inter-Medium.ttf"),
        (700, "Inter-Bold.ttf"),
        (800, "Inter-ExtraBold.ttf"),
    ):
        faces += (
            f"@font-face{{font-family:'{_FONT}';font-weight:{weight};"
            f"src:url(data:font/ttf;base64,{_b64(_ASSETS / fname)}) format('truetype');}}"
        )
    return f"<style>{faces}</style>"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(svg: str, w: int = _W, h: int = _H) -> bytes:
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


# --- vector icons (cx, cy = centre) ------------------------------------------
def _tri_up(cx: int, cy: int) -> str:
    return f'<polygon points="{cx - 13},{cy + 10} {cx + 13},{cy + 10} {cx},{cy - 12}" fill="{_GREEN}"/>'


def _tri_down(cx: int, cy: int) -> str:
    return f'<polygon points="{cx - 13},{cy - 10} {cx + 13},{cy - 10} {cx},{cy + 12}" fill="{_RED}"/>'


def _dot(cx: int, cy: int) -> str:
    return f'<circle cx="{cx}" cy="{cy}" r="12" fill="{_GREY}"/>'


def _barchart(cx: int, cy: int) -> str:
    bars = ""
    for i, h in enumerate((14, 22, 30)):
        x = cx - 18 + i * 13
        bars += f'<rect x="{x}" y="{cy + 15 - h}" width="9" height="{h}" rx="2" fill="{_GOLD}"/>'
    return bars


def _globe(cx: int, cy: int) -> str:
    return (
        f'<g stroke="{_GREY}" stroke-width="2.2" fill="none">'
        f'<circle cx="{cx}" cy="{cy}" r="13"/>'
        f'<ellipse cx="{cx}" cy="{cy}" rx="6" ry="13"/>'
        f'<line x1="{cx - 13}" y1="{cy}" x2="{cx + 13}" y2="{cy}"/></g>'
    )


def _shield(cx: int, cy: int) -> str:
    return (
        f'<path d="M{cx},{cy - 14} L{cx + 12},{cy - 8} L{cx + 12},{cy + 1} '
        f'C{cx + 12},{cy + 10} {cx},{cy + 15} {cx},{cy + 15} '
        f'C{cx},{cy + 15} {cx - 12},{cy + 10} {cx - 12},{cy + 1} '
        f'L{cx - 12},{cy - 8} Z" stroke="{_GREY}" stroke-width="2.2" fill="none"/>'
        f'<path d="M{cx - 5},{cy} L{cx - 1},{cy + 5} L{cx + 6},{cy - 5}" '
        f'stroke="{_GREY}" stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    )


@dataclass
class Mover:
    code: str
    change_pct: float


@dataclass
class EveningWrapData:
    date_label: str
    dsex: float | None
    dsex_change: float | None  # percent
    advancers: int
    decliners: int
    unchanged: int
    turnover_cr: float | None
    movers: list[Mover]


def _fmt(n: float | None, dp: int = 0) -> str:
    return "—" if n is None else f"{n:,.{dp}f}"


def _stat(left: int, icon: str, num: str, label: str, num_color: str) -> str:
    """One stat cell: icon + bold number + muted label, left-aligned at a fixed indent."""
    return (
        f"{icon}"
        f'<text x="{left + 78}" y="{511}" font-family="{_FONT}">'
        f'<tspan font-size="42" font-weight="800" fill="{num_color}">{num}</tspan>'
        f'<tspan dx="11" font-size="30" font-weight="500" fill="{_GREY}">{label}</tspan></text>'
    )


def _mover_row(m: Mover, idx: int, badge_x: int, code_x: int, pct_x: int, y: int) -> str:
    return (
        f'<rect x="{badge_x}" y="{y - 25}" width="40" height="40" rx="9" fill="#1b2230"/>'
        f'<text x="{badge_x + 20}" y="{y - 1}" font-size="22" font-family="{_FONT}" '
        f'font-weight="500" fill="{_GREY}" text-anchor="middle">{idx}</text>'
        f'<text x="{code_x}" y="{y}" font-size="36" font-family="{_FONT}" '
        f'font-weight="700" fill="{_GOLD}">${_esc(m.code)}</text>'
        f'<text x="{pct_x}" y="{y}" font-size="36" font-family="{_FONT}" '
        f'font-weight="800" fill="{_GREEN}" text-anchor="end">{m.change_pct:+.2f}%</text>'
    )


def evening_wrap_card(d: EveningWrapData) -> bytes:
    chg = d.dsex_change
    chg_color = _GREEN if (chg or 0) >= 0 else _RED
    chg_txt = "—" if chg is None else f"{chg:+.2f}%"
    turnover = "—" if d.turnover_cr is None else f"Tk {_fmt(d.turnover_cr)} cr"

    rows = ""
    cols = [(96, 156, 776), (824, 884, 1504)]
    ys = [702, 762, 822]
    for i, m in enumerate(d.movers[:6]):
        bx, cx, px = cols[i // 3]
        rows += _mover_row(m, i + 1, bx, cx, px, ys[i % 3])

    # 4 equal stat columns
    cl = [64, 432, 800, 1168]
    turnover_cell = (
        f"{_barchart(cl[3] + 30, 495)}"
        f'<text x="{cl[3] + 66}" y="511" font-family="{_FONT}">'
        f'<tspan font-size="27" font-weight="500" fill="{_GREY}">Turnover</tspan>'
        f'<tspan dx="9" font-size="29" font-weight="800" fill="{_WHITE}">{_esc(turnover)}</tspan></text>'
    )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{_W}" height="{_H}" viewBox="0 0 {_W} {_H}">
  <defs>{_font_face()}
    <linearGradient id="bg" x1="0" y1="0" x2="0.7" y2="1"><stop offset="0" stop-color="#0d1320"/><stop offset="1" stop-color="#05080e"/></linearGradient>
    <radialGradient id="glow" cx="0.8" cy="0.12" r="0.6"><stop offset="0" stop-color="{_GOLD}" stop-opacity="0.20"/><stop offset="1" stop-color="{_GOLD}" stop-opacity="0"/></radialGradient>
    <linearGradient id="goldline" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{_GOLD}" stop-opacity="0"/><stop offset="1" stop-color="{_GOLD}" stop-opacity="0.85"/></linearGradient>
  </defs>
  <rect width="{_W}" height="{_H}" fill="url(#bg)"/>
  <rect width="{_W}" height="{_H}" fill="url(#glow)"/>

  <!-- header -->
  <image href="{_mark_data_uri()}" x="64" y="50" width="104" height="104"/>
  <text x="188" y="112" font-size="56" font-family="{_FONT}" font-weight="800" fill="{_WHITE}">Bulls of Dhaka</text>
  <text x="190" y="156" font-size="29" font-family="{_FONT}" font-weight="700" fill="{_GOLD}" letter-spacing="8">EVENING WRAP</text>
  <text x="1536" y="108" font-size="34" font-family="{_FONT}" font-weight="500" fill="{_GREY}" text-anchor="end">{_esc(d.date_label)}</text>
  <rect x="1300" y="126" width="236" height="3" rx="1.5" fill="url(#goldline)"/>

  <!-- DSEX -->
  <text x="68" y="250" font-size="34" font-family="{_FONT}" font-weight="500" fill="{_GREY}" letter-spacing="6">DSEX</text>
  <text x="64" y="372" font-size="128" font-family="{_FONT}" font-weight="800" fill="{_WHITE}">{_fmt(d.dsex, 2)}</text>
  <line x1="980" y1="292" x2="980" y2="372" stroke="{_GOLD}" stroke-opacity="0.4" stroke-width="3"/>
  <text x="1030" y="368" font-size="92" font-family="{_FONT}" font-weight="800" fill="{chg_color}">{chg_txt}</text>
  <rect x="64" y="404" width="620" height="3" rx="1.5" fill="url(#goldline)" opacity="0.55"/>

  <!-- stat row -->
  <rect x="64" y="445" width="1472" height="104" rx="18" fill="{_PANEL}" fill-opacity="0.8" stroke="{_BORDER}" stroke-opacity="0.25"/>
  <line x1="432" y1="469" x2="432" y2="525" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="800" y1="469" x2="800" y2="525" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="1168" y1="469" x2="1168" y2="525" stroke="{_SEP}" stroke-opacity="0.08"/>
  {_stat(cl[0], _tri_up(cl[0] + 40, 495), str(d.advancers), "up", _GREEN)}
  {_stat(cl[1], _tri_down(cl[1] + 40, 495), str(d.decliners), "down", _RED)}
  {_stat(cl[2], _dot(cl[2] + 40, 495), str(d.unchanged), "flat", _WHITE)}
  {turnover_cell}

  <!-- top movers -->
  <rect x="64" y="588" width="8" height="34" rx="2" fill="{_GOLD}"/>
  <text x="90" y="617" font-size="32" font-family="{_FONT}" font-weight="800" fill="{_GOLD}" letter-spacing="6">TOP MOVERS</text>
  <rect x="64" y="645" width="1472" height="207" rx="18" fill="{_PANEL}" fill-opacity="0.8" stroke="{_BORDER}" stroke-opacity="0.25"/>
  <line x1="800" y1="672" x2="800" y2="825" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="96" y1="732" x2="776" y2="732" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="96" y1="792" x2="776" y2="792" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="824" y1="732" x2="1504" y2="732" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="824" y1="792" x2="1504" y2="792" stroke="{_SEP}" stroke-opacity="0.08"/>
  {rows}

  <!-- footer -->
  {_globe(80, 873)}
  <text x="106" y="881" font-size="25" font-family="{_FONT}" font-weight="400" fill="{_GREY}">bullsofdhaka.com</text>
  {_shield(1042, 873)}
  <text x="1536" y="881" font-size="24" font-family="{_FONT}" font-weight="400" fill="{_GREY}" text-anchor="end">Informational data, not investment advice</text>
</svg>"""
    return render(svg)
