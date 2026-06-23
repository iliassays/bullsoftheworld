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

log = logging.getLogger(__name__)


class TechnicalsFacts(BaseModel):
    """Computed technicals for one stock — the inputs the explainer narrates (never invents)."""

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


class ExplainerOut(BaseModel):
    explanation: str


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
    return "\n".join(lines)


def _safe_fallback(f: TechnicalsFacts) -> str:
    """Deterministic, advice-free summary if the model trips the compliance gate."""
    parts = [f"${f.code} closed at {f.last_close} on {f.as_of_date}."]
    if f.rsi_14 is not None:
        parts.append(f"RSI is {f.rsi_14:.0f}.")
    if f.nearest_support is not None and f.nearest_resistance is not None:
        parts.append(f"Support ~{f.nearest_support}, resistance ~{f.nearest_resistance}.")
    return " ".join(parts)


async def explain_technicals(facts: TechnicalsFacts, *, language: str = "English") -> str:
    """Return a plain-language, advice-free explanation of the technicals in the given language."""
    system = f"{EXPLAINER_SYSTEM_V1}\n\nWrite the explanation in {language}."
    result = await structured_complete(system, _render(facts), ExplainerOut)
    explanation = result.explanation.strip()

    finding = contains_advice(explanation)
    if finding.is_advice:
        log.warning("explainer tripped no-advice gate for $%s: %s", facts.code, finding.matches)
        return _safe_fallback(facts)
    return explanation
