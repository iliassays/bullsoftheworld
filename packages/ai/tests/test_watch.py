"""Grounding guard for Today's Watch — the LLM may write prose, but every '%' it cites must be a
real price/return move. Regression for the RDFOOD bug: a +12.57 pp ownership delta got relabeled as
a '+12.6%' price surge (the real move was ~+1%)."""

from __future__ import annotations

from bulls.ai.tasks.watch import WatchItem, _allowed_pcts, _ungrounded_pcts

_ITEMS = [
    WatchItem(code="SILVAPHL", change_pct=9.86, posts=3, bull=2, bear=0),
    WatchItem(code="BSRMLTD", change_pct=10.00, posts=2, bull=1, bear=0),
    WatchItem(code="APEXFOOT", change_pct=-0.4, posts=2, bull=0, bear=1),
]
_EXTRAS = [
    "Turnover: Tk 1574 cr, 1.3x the 20-day average.",
    "Sector leaders: Mutual Funds +2.4% avg; laggard: Travel & Leisure -0.7% avg.",
    "- RDFOOD: institutions raised their ownership stake by 12.57 percentage points "
    "(an ownership change at the last disclosure — NOT a price move)",
    "- Strongest 12-month trend: COPPERTECH (+312%)",
]


def test_allowed_excludes_ownership_pp():
    allowed = {abs(a) for a in _allowed_pcts(_ITEMS, _EXTRAS)}
    # Listed price moves, sector averages, and the 12-month trend are allowed…
    assert {9.86, 10.0, 0.4, 2.4, 0.7, 312.0} <= allowed
    # …but the 12.57 pp ownership delta is NOT a price percentage.
    assert 12.57 not in allowed


def test_catches_ownership_pp_written_as_price():
    bad = "RDFOOD surged +12.6% on institutional accumulation, while SILVAPHL +9.86%."
    assert _ungrounded_pcts(bad, _allowed_pcts(_ITEMS, _EXTRAS)) == ["+12.6%"]


def test_passes_grounded_prose_with_worded_direction():
    good = (
        "BSRMLTD +10% and SILVAPHL +9.86% led; Mutual Funds averaged +2.4%. RDFOOD saw "
        "institutions raise their stake 12.57 pp. Travel & Leisure slipped 0.7%."
    )
    assert _ungrounded_pcts(good, _allowed_pcts(_ITEMS, _EXTRAS)) == []


def test_tolerance_allows_rounding():
    items = [WatchItem(code="X", change_pct=9.86, posts=1, bull=1, bear=0)]
    allowed = _allowed_pcts(items, None)
    assert _ungrounded_pcts("X rose almost 10%", allowed) == []  # 10 vs 9.86 within tol
    assert _ungrounded_pcts("X rose 14%", allowed) == ["14%"]  # fabricated
