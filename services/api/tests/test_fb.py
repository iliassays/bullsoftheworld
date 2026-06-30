"""Facebook content tests — pure caption + card render (no DB, no network)."""

from __future__ import annotations

from api.fb import cards
from api.fb.compose import evening_caption, index_pct

_DATA = cards.EveningWrapData(
    date_label="28 Jun 2026",
    dsex=5243.18,
    dsex_change=0.82,
    advancers=227,
    decliners=97,
    unchanged=72,
    turnover_cr=612,
    movers=[cards.Mover("BEXIMCO", 9.86), cards.Mover("WMSHIPYARD", 9.38)],
    losers=[cards.Mover("GP", -4.12), cards.Mover("BRACBANK", -3.25)],
)


def test_evening_caption_is_bilingual_and_descriptive():
    cap = evening_caption(_DATA)
    assert "Evening Wrap" in cap and "ইভিনিং র‍্যাপ" in cap  # EN + BN
    assert "$BEXIMCO" in cap and "5,243" in cap  # cashtag + DSEX
    assert "Top gainers" in cap and "top losers" in cap and "$GP -4.1%" in cap
    assert "See the full Evening Wrap" in cap
    assert "https://bullsofdhaka.com/markets?utm_source=facebook" in cap
    assert "utm_campaign=evening_wrap" in cap
    assert "তথ্যমূলক ডেটা, বিনিয়োগ পরামর্শ নয়।" in cap
    assert "Descriptive data only, not investment advice." in cap
    assert "buy" not in cap.lower() and "sell" not in cap.lower()  # no advice


def test_evening_caption_handles_missing_data():
    blank = cards.EveningWrapData("x", None, None, 0, 0, 0, None, [])
    cap = evening_caption(blank)
    assert "—" in cap and "👉 https://bullsofdhaka.com/markets?utm_source=facebook" in cap


def test_card_renders_png():
    png = cards.evening_wrap_card(_DATA)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # valid PNG header


def test_morning_watch_card_renders_png():
    data = cards.MorningWatchData(
        date_label="30 Jun 2026",
        dsex=5722.54,
        dsex_change=0.05,
        groups=[
            cards.WatchGroup(
                "NEAR 52W HIGH",
                "Close within 5% of high",
                "high",
                [("GP", "0.0%", "from high"), ("SQURPHARMA", "-1.2%", "from high")],
            ),
            cards.WatchGroup(
                "NEAR 52W LOW",
                "Close within 5% of low",
                "low",
                [("RENATA", "1.8%", "from low"), ("BATBC", "3.4%", "from low")],
            ),
            cards.WatchGroup(
                "MOMENTUM",
                "3M trend, last month skipped",
                "momentum",
                [("BEXIMCO", "+42%", "3M"), ("BRACBANK", "+18%", "3M")],
            ),
            cards.WatchGroup(
                "HEAVY VOLUME",
                "5D volume vs 60D avg",
                "volume",
                [("CITYBANK", "3.1x", "5D/60D"), ("ROBI", "2.4x", "5D/60D")],
            ),
        ],
    )
    png = cards.morning_watch_card(data)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # valid PNG header


def test_index_pct_converts_points_and_guards():
    # +35.99 points on 5652.82 ≈ +0.64% (not +35.99%)
    pct = index_pct(5652.82, 35.99)
    assert pct is not None and 0.6 < pct < 0.7
    assert index_pct(5652.82, None) is None
    assert index_pct(5000.0, 2000.0) is None  # implausible (>20%) → omit, don't mislead
