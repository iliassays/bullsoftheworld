"""Plain-language technicals explainer — the educational AI layer over the analytics engine.

The analytics engine computes the FACTS (RSI, support/resistance, trend, 52-week position); this
task asks the LLM only to explain them in plain language for a beginner. Output is run through the
no-advice compliance gate — anything advisory is dropped in favour of a safe deterministic summary.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from bulls.ai.compliance import contains_advice
from bulls.ai.llm import structured_complete
from bulls.ai.prompts.explainer import EXPLAINER_SYSTEM_V1
from bulls.ai.prompts.language import language_directive

log = logging.getLogger(__name__)


class TechnicalsFacts(BaseModel):
    """Computed facts for one stock — the inputs the explainer narrates (never invents). Covers the
    whole picture (chart + fundamentals + ownership) so the AI write-up is a fuller story than the
    deterministic snapshot, not a re-narration of the same technicals."""

    code: str
    name: str
    as_of_date: str
    last_close: float
    above_sma_50: bool | None = None
    above_sma_200: bool | None = None
    rsi_14: float | None = None
    nearest_support: float | None = None
    nearest_resistance: float | None = None
    week52_high: float | None = None
    week52_low: float | None = None
    pct_from_52w_high: float | None = None
    relative_volume: float | None = None
    # Fundamentals + ownership + longer trend — the "story" beyond the chart
    sector: str | None = None
    pe_ratio: float | None = None
    pe_vs_sector: float | None = None
    roe: float | None = None
    eps_growth_yoy: float | None = None
    dividend_yield: float | None = None
    mom_12_1: float | None = None
    smart_money_delta: float | None = None  # institutional + foreign ownership change, pp


class ExplainPoint(BaseModel):
    tag: str  # chart | fundamentals | trend | crowd
    text: str


class ExplainerOut(BaseModel):
    headline: str  # one-line gist of the overall picture
    points: list[ExplainPoint]  # 2-4 short labelled reads


def _render(f: TechnicalsFacts) -> str:
    lines = [
        f"Stock: ${f.code} ({f.name})",
        f"As of {f.as_of_date} close: {f.last_close}",
    ]
    if f.above_sma_50 is not None:
        lines.append(f"50-day moving average: {'above' if f.above_sma_50 else 'below'} it")
    if f.above_sma_200 is not None:
        lines.append(f"200-day moving average: {'above' if f.above_sma_200 else 'below'} it")
    if f.rsi_14 is not None:
        lines.append(f"RSI(14): {f.rsi_14:.0f} (over 70 = overbought zone, under 30 = oversold)")
    if f.nearest_support is not None:
        lines.append(f"Nearest support level: {f.nearest_support}")
    if f.nearest_resistance is not None:
        lines.append(f"Nearest resistance level: {f.nearest_resistance}")
    if f.week52_low is not None and f.week52_high is not None:
        lines.append(f"52-week range: {f.week52_low} to {f.week52_high}")
    if f.pct_from_52w_high is not None:
        lines.append(f"Distance from 52-week high: {f.pct_from_52w_high:.0f}%")
    if f.relative_volume is not None:
        lines.append(f"Volume vs 20-day average: {f.relative_volume:.1f}x")
    if f.sector:
        lines.append(f"Sector: {f.sector}")
    if f.pe_ratio is not None:
        lines.append(f"P/E ratio: {f.pe_ratio:.1f}")
    if f.pe_vs_sector is not None:
        lines.append(f"P/E vs sector median: {f.pe_vs_sector:.2f}x (below 1.0 = cheaper than peers)")
    if f.roe is not None:
        lines.append(f"Return on equity: {f.roe:.0f}% (profit per taka of shareholder capital)")
    if f.eps_growth_yoy is not None:
        lines.append(f"Earnings growth year-on-year: {f.eps_growth_yoy:+.0f}%")
    if f.dividend_yield is not None:
        lines.append(f"Dividend yield: {f.dividend_yield:.1f}%")
    if f.mom_12_1 is not None:
        lines.append(f"12-month price trend (skipping the last month): {f.mom_12_1:+.0f}%")
    if f.smart_money_delta is not None:
        lines.append(
            f"Institutional + foreign ownership change since last disclosure: "
            f"{f.smart_money_delta:+.1f} percentage points"
        )
    return "\n".join(lines)


def _safe_fallback(f: TechnicalsFacts) -> ExplainerOut:
    """Deterministic, advice-free summary if the model trips the compliance gate."""
    points = [
        ExplainPoint(tag="chart", text=f"${f.code} closed at {f.last_close} on {f.as_of_date}."),
    ]
    if f.rsi_14 is not None:
        points.append(ExplainPoint(tag="chart", text=f"RSI is {f.rsi_14:.0f}."))
    if f.nearest_support is not None and f.nearest_resistance is not None:
        points.append(
            ExplainPoint(
                tag="chart", text=f"Support ~{f.nearest_support}, resistance ~{f.nearest_resistance}."
            )
        )
    return ExplainerOut(headline=f"${f.code} snapshot ({f.as_of_date})", points=points)


async def explain_technicals(facts: TechnicalsFacts, *, language: str = "English") -> ExplainerOut:
    """A scannable, advice-free read: one-line headline + 2-4 short labelled points."""
    system = f"{EXPLAINER_SYSTEM_V1}\n\n{language_directive(language)}"
    result = await structured_complete(system, _render(facts), ExplainerOut)

    blob = result.headline + " " + " ".join(p.text for p in result.points)
    finding = contains_advice(blob)
    if finding.is_advice:
        log.warning("explainer tripped no-advice gate for $%s: %s", facts.code, finding.matches)
        return _safe_fallback(facts)
    return result
