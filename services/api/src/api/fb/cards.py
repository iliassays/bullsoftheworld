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
from dataclasses import dataclass, field
from pathlib import Path

_ASSETS = Path(__file__).parent / "assets"
_MARK = _ASSETS / "mark.png"
_FONT = "Inter"
# Palette mirrors the web app's @theme tokens (apps/web/src/index.css) so cards match the in-app UI.
_GOLD = "#f5b82e"  # --color-accent
_GREEN = "#16c784"  # --color-up
_RED = "#ea3943"  # --color-down
_WHITE = "#e8edf2"  # --color-text
_GREY = "#8b97a6"  # --color-muted
_BG = "#0b0e11"  # --color-bg
_PANEL = "#07111d"  # panel fill, rendered at 0.8 opacity
_BORDER = _GOLD  # at 0.35 opacity — one border style everywhere
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
    return (
        f'<polygon points="{cx - 13},{cy - 10} {cx + 13},{cy - 10} {cx},{cy + 12}" fill="{_RED}"/>'
    )


def _dot(cx: int, cy: int) -> str:
    return f'<circle cx="{cx}" cy="{cy}" r="12" fill="{_GREY}"/>'


def _barchart(cx: int, cy: int, color: str = _GOLD) -> str:
    bars = ""
    for i, h in enumerate((14, 22, 30)):
        x = cx - 18 + i * 13
        bars += f'<rect x="{x}" y="{cy + 15 - h}" width="9" height="{h}" rx="2" fill="{color}"/>'
    return bars


def _ic_peak(cx: int, cy: int, color: str = _GOLD) -> str:  # near 52w high (mountain)
    return f'<polygon points="{cx - 18},{cy + 12} {cx - 5},{cy - 11} {cx + 2},{cy} {cx + 11},{cy - 15} {cx + 18},{cy + 12}" fill="{color}"/>'


def _ic_uptrend(cx: int, cy: int, color: str = _GOLD) -> str:  # rising trend + arrow
    return (
        f'<polyline points="{cx - 18},{cy + 9} {cx - 4},{cy - 3} {cx + 3},{cy + 3} {cx + 16},{cy - 13}" '
        f'fill="none" stroke="{color}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<polygon points="{cx + 8},{cy - 15} {cx + 19},{cy - 17} {cx + 17},{cy - 6}" fill="{color}"/>'
    )


def _ic_low(cx: int, cy: int, color: str = _GOLD) -> str:  # close to 52w low / support zone
    return (
        f'<polyline points="{cx - 18},{cy - 9} {cx - 5},{cy + 4} {cx + 6},{cy + 4} {cx + 18},{cy - 9}" '
        f'fill="none" stroke="{color}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<line x1="{cx - 20}" y1="{cy + 14}" x2="{cx + 20}" y2="{cy + 14}" '
        f'stroke="{color}" stroke-width="3.5" stroke-linecap="round"/>'
    )


def _ic_coins(cx: int, cy: int, color: str = _GOLD) -> str:  # turnover (stacked coins)
    out = ""
    for dy in (11, 0, -11):
        out += (
            f'<ellipse cx="{cx}" cy="{cy + dy}" rx="15" ry="5.5" fill="{color}" '
            f'stroke="{_BG}" stroke-width="1.5"/>'
        )
    return out


_QUAD_ICONS = {
    "high": _ic_uptrend,
    "low": _ic_low,
    "momentum": _ic_uptrend,
    "volume": _barchart,
    "turnover": _ic_coins,
    "gainers": _ic_uptrend,
}


def _info(cx: int, cy: int) -> str:
    return (
        f'<circle cx="{cx}" cy="{cy}" r="12" fill="none" stroke="{_GOLD}" stroke-width="2.2"/>'
        f'<circle cx="{cx}" cy="{cy - 5}" r="1.7" fill="{_GOLD}"/>'
        f'<line x1="{cx}" y1="{cy - 1}" x2="{cx}" y2="{cy + 6}" stroke="{_GOLD}" stroke-width="2.4" stroke-linecap="round"/>'
    )


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
        f"C{cx + 12},{cy + 10} {cx},{cy + 15} {cx},{cy + 15} "
        f"C{cx},{cy + 15} {cx - 12},{cy + 10} {cx - 12},{cy + 1} "
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
    losers: list[Mover] = field(default_factory=list)


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


def _mover_row(
    m: Mover,
    idx: int,
    badge_x: int,
    code_x: int,
    pct_x: int,
    y: int,
    color: str = _GREEN,
) -> str:
    return (
        f'<rect x="{badge_x}" y="{y - 25}" width="40" height="40" rx="9" fill="#1b2230"/>'
        f'<text x="{badge_x + 20}" y="{y - 1}" font-size="22" font-family="{_FONT}" '
        f'font-weight="500" fill="{_GREY}" text-anchor="middle">{idx}</text>'
        f'<text x="{code_x}" y="{y}" font-size="36" font-family="{_FONT}" '
        f'font-weight="700" fill="{_GOLD}">${_esc(m.code)}</text>'
        f'<text x="{pct_x}" y="{y}" font-size="36" font-family="{_FONT}" '
        f'font-weight="800" fill="{color}" text-anchor="end">{m.change_pct:+.2f}%</text>'
    )


def _panel(x: int, y: int, w: int, h: int, r: int = 16) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" '
        f'fill="{_PANEL}" fill-opacity="0.8" stroke="{_BORDER}" stroke-opacity="0.35"/>'
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
  <line x1="64" y1="838" x2="1536" y2="838" stroke="{_SEP}" stroke-opacity="0.08"/>
  {_globe(80, 873)}
  <text x="106" y="881" font-size="24" font-family="{_FONT}" font-weight="400" fill="{_GREY}">bullsofdhaka.com</text>
  <line x1="340" y1="858" x2="340" y2="888" stroke="{_SEP}" stroke-opacity="0.10"/>
  {_info(372, 873)}
  <text x="396" y="881" font-size="23" font-family="{_FONT}"><tspan font-weight="700" fill="{_GOLD}">DATA ONLY.</tspan><tspan dx="8" font-weight="400" fill="{_GREY}">Not investment advice.</tspan></text>
  <text x="1536" y="881" font-size="21" font-family="{_FONT}" font-weight="400" fill="{_GREY}" text-anchor="end">DSE EOD data · subject to correction</text>
</svg>"""


def evening_wrap_card(d: EveningWrapData) -> bytes:
    chg = d.dsex_change
    chg_color = _GREEN if (chg or 0) >= 0 else _RED
    chg_txt = "—" if chg is None else f"{chg:+.2f}%"
    turnover = "—" if d.turnover_cr is None else f"Tk {_fmt(d.turnover_cr)} cr"

    gainer_rows = ""
    loser_rows = ""
    ys = [702, 762, 822]
    for i, m in enumerate(d.movers[:3]):
        gainer_rows += _mover_row(m, i + 1, 96, 156, 776, ys[i], _GREEN)
    for i, m in enumerate(d.losers[:3]):
        loser_rows += _mover_row(m, i + 1, 824, 884, 1504, ys[i], _RED)

    # Turnover ("Turnover Tk 1,574 cr") is far wider than the up/down/flat numbers, so its column
    # starts earlier and is wider — borrowing the slack the short stat cells leave on their right.
    cl = [64, 432, 800, 1060]
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
  <line x1="1060" y1="469" x2="1060" y2="525" stroke="{_SEP}" stroke-opacity="0.08"/>
  {_stat(cl[0], _tri_up(cl[0] + 40, 495), str(d.advancers), "up", _GREEN)}
  {_stat(cl[1], _tri_down(cl[1] + 40, 495), str(d.decliners), "down", _RED)}
  {_stat(cl[2], _dot(cl[2] + 40, 495), str(d.unchanged), "flat", _WHITE)}
  {turnover_cell}
  {_section(64, 614, "TOP GAINERS")}
  {_section(824, 614, "TOP LOSERS")}
  {_panel(64, 645, 1472, 207)}
  <line x1="800" y1="672" x2="800" y2="825" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="96" y1="732" x2="776" y2="732" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="96" y1="792" x2="776" y2="792" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="824" y1="732" x2="1504" y2="732" stroke="{_SEP}" stroke-opacity="0.08"/>
  <line x1="824" y1="792" x2="1504" y2="792" stroke="{_SEP}" stroke-opacity="0.08"/>
  {gainer_rows}
  {loser_rows}"""
    return render(_frame("EVENING WRAP", d.date_label, inner))


# --- Morning Watch -----------------------------------------------------------
@dataclass
class WatchGroup:
    label: str
    subtitle: str
    icon: str  # key into _QUAD_ICONS: volume | high | turnover | gainers
    items: list[tuple[str, str, str]]  # (code, value, unit)
    accent: str = _GOLD  # icon + ring colour
    value_color: str = _GREEN  # metric value colour


@dataclass
class MorningWatchData:
    date_label: str
    dsex: float | None
    dsex_change: float | None  # last close %, points already converted
    groups: list[WatchGroup]  # 4 quadrants


def morning_watch_card(d: MorningWatchData) -> bytes:
    chg = d.dsex_change
    chg_color = _GREEN if (chg or 0) >= 0 else _RED
    arrow = "▲" if (chg or 0) >= 0 else "▼"
    dsex = _fmt(d.dsex, 2)
    chg_txt = "" if chg is None else f"({chg:+.2f}%) {arrow}"

    pw, ph = 720, 248
    pos = [(64, 316), (816, 316), (64, 576), (816, 576)]  # TL, TR, BL, BR
    panels = ""
    for i, g in enumerate(d.groups[:4]):
        x, y = pos[i]
        icon = _QUAD_ICONS.get(g.icon, _ic_uptrend)
        panels += _panel(x, y, pw, ph)
        panels += f'<circle cx="{x + 62}" cy="{y + 60}" r="32" fill="none" stroke="{g.accent}" stroke-width="2.5"/>'
        panels += icon(x + 62, y + 60, g.accent)
        panels += (
            f'<text x="{x + 116}" y="{y + 52}" font-size="30" font-family="{_FONT}" '
            f'font-weight="800" fill="{g.accent}" letter-spacing="1">{_esc(g.label)}</text>'
            f'<text x="{x + 116}" y="{y + 84}" font-size="22" font-family="{_FONT}" '
            f'font-weight="400" fill="{_GREY}">{_esc(g.subtitle)}</text>'
        )
        panels += f'<line x1="{x + 30}" y1="{y + 106}" x2="{x + pw - 30}" y2="{y + 106}" stroke="{_SEP}" stroke-opacity="0.08"/>'
        for j, (code, value, unit) in enumerate(g.items[:3]):
            ry = y + 150 + j * 42
            panels += (
                f'<rect x="{x + 30}" y="{ry - 25}" width="38" height="38" rx="9" fill="#1b2230"/>'
                f'<text x="{x + 49}" y="{ry - 1}" font-size="20" font-family="{_FONT}" '
                f'font-weight="500" fill="{_GREY}" text-anchor="middle">{j + 1}</text>'
                f'<text x="{x + 88}" y="{ry}" font-size="32" font-family="{_FONT}" '
                f'font-weight="700" fill="{_GOLD}">${_esc(code)}</text>'
                f'<text x="{x + pw - 30}" y="{ry}" font-family="{_FONT}" text-anchor="end">'
                f'<tspan font-size="26" font-weight="700" fill="{g.value_color}">{_esc(value)}</tspan>'
                f'<tspan dx="7" font-size="23" font-weight="500" fill="{_GREY}">{_esc(unit)}</tspan></text>'
            )

    inner = f"""
  <text x="64" y="208" font-size="38" font-family="{_FONT}" font-weight="500" fill="{_GREY}">Last close · <tspan fill="{_WHITE}" font-weight="800">DSEX {dsex}</tspan> <tspan fill="{chg_color}" font-weight="800">{chg_txt}</tspan></text>
  <text x="64" y="244" font-size="24" font-family="{_FONT}" font-weight="400" fill="{_GREY}">Based on previous trading day data</text>
  {_section(64, 296, "ON THE RADAR TODAY")}
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
