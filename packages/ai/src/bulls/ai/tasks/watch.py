"""Today's Watch — an AI note highlighting notable stocks from the day's activity.

Like the digest: the caller computes the ranked facts (movers + chatter) in code; the LLM only
writes the prose naming them. One LLM call for the whole note (cheap, cacheable daily).
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel

from bulls.ai.compliance import contains_advice
from bulls.ai.llm import structured_complete
from bulls.ai.prompts.language import language_directive
from bulls.ai.prompts.watch import WATCH_SYSTEM_V2
from bulls.core.config import get_settings

log = logging.getLogger(__name__)


class WatchItem(BaseModel):
    code: str
    change_pct: float
    posts: int
    bull: int
    bear: int


class Breadth(BaseModel):
    """Market-wide up/down tally for the session."""

    advancers: int
    decliners: int
    unchanged: int
    total: int


class WatchOut(BaseModel):
    summary: str


def _render(items: list[WatchItem], breadth: Breadth | None, extras: list[str] | None) -> str:
    lines: list[str] = []
    if breadth and breadth.total:
        lines.append(
            f"Market breadth: {breadth.advancers} up, {breadth.decliners} down, "
            f"{breadth.unchanged} unchanged (of {breadth.total} traded)."
        )
    # Extra computed facts (turnover, sector leaders, factor standouts) — already grounded.
    lines.extend(extras or [])
    lines.append("Active / moving stocks:")
    for it in items:
        lines.append(
            f"- {it.code}: {it.change_pct:+.2f}%, {it.posts} posts "
            f"({it.bull} bull / {it.bear} bear)"
        )
    return "\n".join(lines)


def _fallback(
    items: list[WatchItem], breadth: Breadth | None = None, *, language: str = "English"
) -> str:
    """Deterministic, localized, advice-free note for disabled/unavailable generation."""
    top = sorted(items, key=lambda i: abs(i.change_pct), reverse=True)[:3]
    movers = ", ".join(f"${i.code} {i.change_pct:+.1f}%" for i in top)
    if language.startswith("Bengali"):
        prefix = (
            f"বাজারে {breadth.advancers}টি শেয়ার বেড়েছে, {breadth.decliners}টি কমেছে। "
            if breadth and breadth.total
            else ""
        )
        return f"{prefix}উল্লেখযোগ্য দামের মুভ: {movers}।"
    prefix = (
        f"Market breadth: {breadth.advancers} advanced and {breadth.decliners} declined. "
        if breadth and breadth.total
        else ""
    )
    return f"{prefix}Notable price moves: {movers}."


# Numbers written with a "%" must be real price/return moves. Ownership deltas (given as "pp") are
# deliberately excluded from the allowed set, so the model cannot relabel a +12.57 pp stake change
# as a "+12.6%" price surge (the RDFOOD bug). x-multiples ("1.3x"), counts, and "pp" stay unchecked.
_PCT_IN_TEXT = re.compile(r"[-+]?\d+(?:\.\d+)?(?=\s*%)")
_PCT_IN_FACT = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*%")


def _allowed_pcts(items: list[WatchItem], extras: list[str] | None) -> list[float]:
    """Price/return percentages the note is allowed to cite: each stock's listed move, plus any
    %-suffixed figure in the grounded fact lines (sector averages, 12-month trend). pp is excluded."""
    allowed = [it.change_pct for it in items]
    for line in extras or []:
        allowed += [float(m) for m in _PCT_IN_FACT.findall(line)]
    return allowed


def _ungrounded_pcts(summary: str, allowed: list[float], *, tol: float = 0.6) -> list[str]:
    """Return any '%' figures in the prose whose magnitude doesn't match a real price/return figure
    (± tol). Magnitude, not signed value: prose often carries direction in words ("slipped 0.7%")
    and writes the number unsigned — that's fine; a fabricated magnitude like 12.6 is what we catch."""
    bad = []
    mags = [abs(a) for a in allowed]
    for tok in _PCT_IN_TEXT.findall(summary):
        v = abs(float(tok))
        if not any(abs(v - m) <= tol for m in mags):
            bad.append(f"{tok}%")
    return bad


async def todays_watch(
    items: list[WatchItem],
    *,
    breadth: Breadth | None = None,
    extras: list[str] | None = None,
    language: str = "English",
) -> str:
    """Grounded 2-3 sentence watch note in the requested language.

    `extras` are extra pre-computed fact lines (turnover, sector leaders, factor standouts) the
    caller assembles in code; the model only weaves them into prose. Output passes the no-advice
    compliance gate; anything advisory is replaced with a safe deterministic movers list.
    """
    if not items:
        return ""
    if get_settings().ai_provider == "disabled":
        return _fallback(items, breadth, language=language)
    system = f"{WATCH_SYSTEM_V2}\n\n{language_directive(language)}"
    user = _render(items, breadth, extras)
    allowed = _allowed_pcts(items, extras)

    try:
        result = await structured_complete(system, user, WatchOut)
    except Exception:
        log.exception("today's watch generation unavailable; using deterministic fallback")
        return _fallback(items, breadth, language=language)
    summary = result.summary.strip()

    # Hard grounding gate: every "%" in the prose must be a real price/return move. If the model
    # invented or mislabeled one (e.g. an ownership pp written as a price %), regenerate once with
    # the offending figures called out, then fall back to the deterministic note if it still fails.
    bad = _ungrounded_pcts(summary, allowed)
    if bad:
        log.warning("today's watch cited unsupported %% %s; regenerating", bad)
        correction = (
            f"{user}\n\nA previous draft stated {', '.join(bad)}, which is NOT supported by the "
            "data above (likely an ownership 'pp' figure written as a price '%'). Rewrite using "
            "only the price percentages explicitly listed beside each stock."
        )
        try:
            result = await structured_complete(system, correction, WatchOut)
        except Exception:
            log.exception("today's watch correction unavailable; using deterministic fallback")
            return _fallback(items, breadth, language=language)
        summary = result.summary.strip()
        if _ungrounded_pcts(summary, allowed):
            log.warning("today's watch still ungrounded; using fallback")
            return _fallback(items, breadth, language=language)

    if contains_advice(summary).is_advice:
        log.warning("today's watch tripped no-advice gate; using fallback")
        return _fallback(items, breadth, language=language)
    return summary
