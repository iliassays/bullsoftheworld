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


def _panel(x: int, y: int, w: int, h: int, r: int = 18) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" '
        f'fill="{_PANEL}" fill-opacity="0.8" stroke="{_BORDER}" stroke-opacity="0.25"/>'
    )


def _section(x: int, y: int, text: str) -> str:
    return (
        f'<rect x="{x}" y="{y - 23}" width="8" height="32" rx="2" fill="{_GOLD}"/>'
        f'<text x="{x + 26}" y="{y}" font-size="32" font-family="{_FONT}" '
        f'font-weight="800" fill="{_GOLD}" letter-spacing="5">{text}</text>'
    )


def _frame(subtitle: str, date_label: str, inner: str) -> str:
    """Common card chrome (defs, background, header, footer); pillars supply `inner`."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{_W}" height="{_H}" viewBox="0 0 {_W} {_H}">
  <defs>{_font_face()}
    <linearGradient id="bg" x1="0" y1="0" x2="0.7" y2="1"><stop offset="0" stop-color="#0d1320"/><stop offset="1" stop-color="#05080e"/></linearGradient>
    <radialGradient id="glow" cx="0.8" cy="0.12" r="0.6"><stop offset="0" stop-color="{_GOLD}" stop-opacity="0.20"/><stop offset="1" stop-color="{_GOLD}" stop-opacity="0"/></radialGradient>
    <linearGradient id="goldline" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{_GOLD}" stop-opacity="0"/><stop offset="1" stop-color="{_GOLD}" stop-opacity="0.85"/></linearGradient>
  </defs>
  <rect width="{_W}" height="{_H}" fill="url(#bg)"/>
  <rect width="{_W}" height="{_H}" fill="url(#glow)"/>
  <image href="{_mark_data_uri()}" x="64" y="50" width="104" height="104"/>
  <text x="188" y="112" font-size="56" font-family="{_FONT}" font-weight="800" fill="{_WHITE}">Bulls of Dhaka</text>
  <text x="190" y="156" font-size="29" font-family="{_FONT}" font-weight="700" fill="{_GOLD}" letter-spacing="8">{_esc(subtitle)}</text>
  <text x="1536" y="108" font-size="34" font-family="{_FONT}" font-weight="500" fill="{_GREY}" text-anchor="end">{_esc(date_label)}</text>
  <rect x="1240" y="126" width="296" height="3" rx="1.5" fill="url(#goldline)"/>
  {inner}
  {_globe(80, 873)}
  <text x="106" y="881" font-size="25" font-family="{_FONT}" font-weight="400" fill="{_GREY}">bullsofdhaka.com</text>
  {_shield(1042, 873)}
  <text x="1536" y="881" font-size="24" font-family="{_FONT}" font-weight="400" fill="{_GREY}" text-anchor="end">Informational data, not investment advice</text>
</svg>"""


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

    cl = [64, 432, 800, 1168]
    turnover_cell = (
        f"{_barchart(cl[3] + 30, 495)}"
        f'<text x="{cl[3] + 66}" y="511" font-family="{_FONT}">'
        f'<tspan font-size="27" font-weight="500" fill="{_GREY}">Turnover</tspan>'
        f'<tspan dx="9" font-size="29" font-weight="800" fill="{_WHITE}">{_esc(turnover)}</tspan></text>'
    )

    inner = f"""
  <text x="68" y="250" font-size="34" font-family="{_FONT}" font-weight="500" fill="{_GREY}" letter-spacing="6">DSEX</text>
  <text x="64" y="372" font-size="128" font-family="{_FONT}" font-weight="800" fill="{_WHITE}">{_fmt(d.dsex, 2)}</text>
  <line x1="980" y1="292" x2="980" y2="372" stroke="{_GOLD}" stroke-opacity="0.4" stroke-width="3"/>
  <text x="1030" y="368" font-size="92" font-family="{_FONT}" font-weight="800" fill="{chg_color}">{chg_txt}</text>
  <rect x="64" y="404" width="620" height="3" rx="1.5" fill="url(#goldline)" opacity="0.55"/>
  {_panel(64, 445, 1472, 104)}
  <line x1="432" y1="469" x2="432" y2="525" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="800" y1="469" x2="800" y2="525" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="1168" y1="469" x2="1168" y2="525" stroke="{_SEP}" stroke-opacity="0.08"/>
  {_stat(cl[0], _tri_up(cl[0] + 40, 495), str(d.advancers), "up", _GREEN)}
  {_stat(cl[1], _tri_down(cl[1] + 40, 495), str(d.decliners), "down", _RED)}
  {_stat(cl[2], _dot(cl[2] + 40, 495), str(d.unchanged), "flat", _WHITE)}
  {turnover_cell}
  {_section(64, 614, "TOP MOVERS")}
  {_panel(64, 645, 1472, 207)}
  <line x1="800" y1="672" x2="800" y2="825" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="96" y1="732" x2="776" y2="732" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="96" y1="792" x2="776" y2="792" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="824" y1="732" x2="1504" y2="732" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="824" y1="792" x2="1504" y2="792" stroke="{_SEP}" stroke-opacity="0.08"/>
  {rows}"""
    return render(_frame("EVENING WRAP", d.date_label, inner))


# --- Morning Watch -----------------------------------------------------------
@dataclass
class WatchGroup:
    label: str
    items: list[tuple[str, str]]  # (code, small metric text)


@dataclass
class MorningWatchData:
    date_label: str
    dsex: float | None
    dsex_change: float | None  # last close %, points already converted
    groups: list[WatchGroup]  # exactly 3 columns


def morning_watch_card(d: MorningWatchData) -> bytes:
    chg = d.dsex_change
    chg_color = _GREEN if (chg or 0) >= 0 else _RED
    dsex = _fmt(d.dsex, 2)
    chg_txt = "" if chg is None else f"({chg:+.2f}%)"

    panels = ""
    px = [64, 564, 1064]
    pw = 472
    for i, g in enumerate(d.groups[:3]):
        x = px[i]
        panels += _panel(x, 345, pw, 470)
        panels += (
            f'<text x="{x + 34}" y="{400}" font-size="27" font-family="{_FONT}" '
            f'font-weight="800" fill="{_GOLD}" letter-spacing="3">{_esc(g.label)}</text>'
        )
        panels += f'<line x1="{x + 30}" y1="420" x2="{x + pw - 30}" y2="420" stroke="{_SEP}" stroke-opacity="0.10"/>'
        for j, (code, metric) in enumerate(g.items[:3]):
            ry = 488 + j * 100
            panels += (
                f'<text x="{x + 34}" y="{ry}" font-size="38" font-family="{_FONT}" '
                f'font-weight="700" fill="{_GOLD}">${_esc(code)}</text>'
                f'<text x="{x + 34}" y="{ry + 34}" font-size="24" font-family="{_FONT}" '
                f'font-weight="500" fill="{_GREY}">{_esc(metric)}</text>'
            )

    inner = f"""
  <text x="64" y="232" font-size="36" font-family="{_FONT}" font-weight="500" fill="{_GREY}">Last close · <tspan fill="{_WHITE}" font-weight="800">DSEX {dsex}</tspan> <tspan fill="{chg_color}" font-weight="800">{chg_txt}</tspan></text>
  {_section(64, 312, "ON THE RADAR TODAY")}
  {panels}"""
    return render(_frame("MORNING WATCH", d.date_label, inner))


# --- Weekly Recap ------------------------------------------------------------
@dataclass
class WeeklyRecapData:
    range_label: str  # e.g. "22-25 Jun 2026"
    dsex_week_pct: float | None
    gainers: list[Mover]
    losers: list[Mover]
    lead_sector: str | None = None
    lag_sector: str | None = None


def _recap_rows(items: list[Mover], color: str, bx: int, cx: int, px: int) -> str:
    out = ""
    ys = [524, 588, 652]
    for i, m in enumerate(items[:3]):
        y = ys[i]
        out += (
            f'<rect x="{bx}" y="{y - 25}" width="40" height="40" rx="9" fill="#1b2230"/>'
            f'<text x="{bx + 20}" y="{y - 1}" font-size="22" font-family="{_FONT}" '
            f'font-weight="500" fill="{_GREY}" text-anchor="middle">{i + 1}</text>'
            f'<text x="{cx}" y="{y}" font-size="36" font-family="{_FONT}" '
            f'font-weight="700" fill="{_GOLD}">${_esc(m.code)}</text>'
            f'<text x="{px}" y="{y}" font-size="36" font-family="{_FONT}" '
            f'font-weight="800" fill="{color}" text-anchor="end">{m.change_pct:+.2f}%</text>'
        )
    return out


def weekly_recap_card(d: WeeklyRecapData) -> bytes:
    wk = d.dsex_week_pct
    wk_color = _GREEN if (wk or 0) >= 0 else _RED
    wk_txt = "—" if wk is None else f"{wk:+.2f}%"
    sector = ""
    if d.lead_sector or d.lag_sector:
        sector = (
            f'<text x="64" y="828" font-size="28" font-family="{_FONT}" font-weight="500" fill="{_GREY}">'
            f'Leading sector <tspan fill="{_GREEN}" font-weight="700">{_esc(d.lead_sector or "—")}</tspan>'
            f'  ·  Lagging <tspan fill="{_RED}" font-weight="700">{_esc(d.lag_sector or "—")}</tspan></text>'
        )

    inner = f"""
  <text x="68" y="232" font-size="34" font-family="{_FONT}" font-weight="500" fill="{_GREY}" letter-spacing="4">DSEX THIS WEEK</text>
  <text x="64" y="340" font-size="108" font-family="{_FONT}" font-weight="800" fill="{wk_color}">{wk_txt}</text>
  <rect x="64" y="372" width="560" height="3" rx="1.5" fill="url(#goldline)" opacity="0.55"/>
  {_section(64, 432, "TOP GAINERS")}
  {_section(800, 432, "TOP LOSERS")}
  {_panel(64, 460, 712, 232)}
  {_panel(800, 460, 712, 232)}
  <line x1="96" y1="552" x2="744" y2="552" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="96" y1="616" x2="744" y2="616" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="832" y1="552" x2="1480" y2="552" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="832" y1="616" x2="1480" y2="616" stroke="{_SEP}" stroke-opacity="0.08"/>
  {_recap_rows(d.gainers, _GREEN, 96, 156, 744)}
  {_recap_rows(d.losers, _RED, 832, 892, 1480)}
  {sector}"""
    return render(_frame("WEEK IN REVIEW", d.range_label, inner))
