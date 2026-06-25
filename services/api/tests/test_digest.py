"""Unit tests for the deterministic digest templates.

Pure functions over SymbolFacts — no DB, no LLM, so they always run. They lock in the fixes for
the failures the old LLM prose produced: wrong units ("points" / "$"), garbled finance Bangla,
ambiguous numbers, and editorial color ("only N posts").
"""

from __future__ import annotations

from api.routers.digest import _render_digest_bn, _render_digest_en
from bulls.ai.tasks.digest import SymbolFacts


def _facts(**overrides) -> SymbolFacts:
    base = dict(code="GP", name="Grameenphone", last_price=207.0, change_pct_1d=9.47, last_volume=0)
    base.update(overrides)
    return SymbolFacts(**base)


def test_currency_and_units_are_correct():
    f = _facts(change_pct_5d=3.2, last_volume=1600, avg_volume_5d=1000, bull_posts=5, bear_posts=2)
    for render in (_render_digest_en, _render_digest_bn):
        s = render(f)
        assert "৳207" in s  # taka, not $ and not "points"
        assert "$" not in s
        assert "point" not in s.lower()
        assert "পয়েন্ট" not in s


def test_no_editorializing_words():
    # The old LLM said "only 7 bullish comments" — a judgment, not a fact. Templates never do.
    f = _facts(bull_posts=7, bear_posts=0, neutral_posts=0)
    assert "only" not in _render_digest_en(f).lower()
    assert "শুধুমাত্র" not in _render_digest_bn(f)


def test_direction_verbs_and_crowd():
    up = _facts(change_pct_1d=9.47, bull_posts=8, bear_posts=1)
    assert "rose 9.47%" in _render_digest_en(up)
    assert "9.47% বেড়েছে" in _render_digest_bn(up)
    assert "8▲ / 1▼" in _render_digest_en(up)

    down = _facts(change_pct_1d=-4.3)
    assert "fell 4.30%" in _render_digest_en(down)
    assert "4.30% কমেছে" in _render_digest_bn(down)

    flat = _facts(change_pct_1d=0.03)
    assert "little changed" in _render_digest_en(flat)
    assert "অপরিবর্তিত" in _render_digest_bn(flat)


def test_no_posts_states_absence():
    f = _facts(bull_posts=0, bear_posts=0, neutral_posts=0)
    assert "No posts" in _render_digest_en(f)
    assert "কোনো পোস্ট নেই" in _render_digest_bn(f)
