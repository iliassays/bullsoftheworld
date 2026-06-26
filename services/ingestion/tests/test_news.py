"""Unit tests for news classification, strength, and the (scaffold) parser."""

from __future__ import annotations

from bulls.market_data.providers.dse_scrape import parse_news
from ingestion.news import classify, strength
from ingestion.signals.news_agents import render as render_news


def test_classify_taxonomy():
    assert classify("Cash Dividend Declared 25%") == "dividend"
    assert (
        classify("Board Meeting to consider Half Yearly Accounts") == "board_meeting"
    )  # heads-up, not the declaration
    assert classify("Credit Rating assigned to the company") == "rating"
    assert classify("Q3 un-audited financial statement") == "earnings"
    assert classify("Trading suspension of the shares") == "halt"
    assert classify("AGM record date notice") == "corporate_action"
    # noise is dropped
    assert classify("Spot market trading notice") == "noise"
    assert classify("No undisclosed price sensitive information") == "noise"


def test_strength_boosters():
    assert strength("rating", "Credit Rating downgraded to A") == 85  # 60 + 25
    assert strength("rating", "Credit Rating upgraded to AA") == 70  # 60 + 10
    assert strength("earnings", "reported a net loss") == 80  # 65 + 15
    assert strength("dividend", "Interim cash dividend") == 80  # 70 + 10
    assert strength("dividend", "Cash dividend") == 70


def test_parse_news_expected_shape():
    # synthetic — mirrors the EXPECTED news_archive.php table; replace with a real capture to confirm
    html = """
    <table>
      <tr><th>News Date</th><th>Trading Code</th><th>News Title</th></tr>
      <tr><td>2026-06-25</td><td>gp</td><td>Cash Dividend Declared 25%</td></tr>
      <tr><td>Jun 24, 2026</td><td>BEXIMCO</td><td>Board Meeting Notice</td></tr>
    </table>
    """
    items = parse_news(html)
    assert len(items) == 2
    assert items[0].code == "GP" and items[0].headline.startswith("Cash Dividend")
    assert items[1].published_at.day == 24


def test_news_agent_render_quotes_headline_no_advice():
    hl = "Cash Dividend Declared 25%"
    en = render_news("dividend", hl, "GP", "en")
    bn = render_news("dividend", hl, "GP", "bn")
    assert "GP" in en and hl in en and "Not advice" in en
    assert hl in bn and "পরামর্শ নয়" in bn
    for txt in (en, bn):
        assert "buy" not in txt.lower() and "sell" not in txt.lower()
