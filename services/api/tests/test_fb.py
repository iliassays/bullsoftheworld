"""Facebook content tests — pure caption + card render (no DB, no network)."""

from __future__ import annotations

from api.fb import cards
from api.fb.compose import evening_caption

_DATA = cards.EveningWrapData(
    date_label="28 Jun 2026",
    dsex=5243.18,
    dsex_change=0.82,
    advancers=227,
    decliners=97,
    unchanged=72,
    turnover_cr=612,
    movers=[cards.Mover("BEXIMCO", 9.86), cards.Mover("WMSHIPYARD", 9.38)],
)


def test_evening_caption_is_bilingual_and_descriptive():
    cap = evening_caption(_DATA)
    assert "Evening Wrap" in cap and "ইভিনিং র‍্যাপ" in cap  # EN + BN
    assert "$BEXIMCO" in cap and "5,243" in cap  # cashtag + DSEX
    assert "তথ্যমূলক, পরামর্শ নয়।" in cap and "Descriptive data, not advice." in cap
    assert "buy" not in cap.lower() and "sell" not in cap.lower()  # no advice


def test_evening_caption_handles_missing_data():
    blank = cards.EveningWrapData("x", None, None, 0, 0, 0, None, [])
    cap = evening_caption(blank)
    assert "—" in cap and "👉 https://bullsofdhaka.com" in cap


def test_card_renders_png():
    png = cards.evening_wrap_card(_DATA)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # valid PNG header
