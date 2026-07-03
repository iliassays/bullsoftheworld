"""News-desk note rendering — decoded numbers must lead; raw headline is the fallback only."""

from __future__ import annotations

from ingestion.signals.news_agents import render


def test_earnings_note_leads_with_decoded_eps() -> None:
    details = {"eps_current": 1.72, "eps_prior": 1.45, "period": "Q3", "nav": 57.0}
    en = render("earnings", "RAW DSE HEADLINE", "OLYMPIC", "en", details)
    assert "Q3 EPS ৳1.72" in en
    assert "৳1.45 a year earlier" in en
    assert "(+19%)" in en
    assert "NAV ৳57" in en
    assert "RAW DSE HEADLINE" not in en  # decoded facts replace the raw headline
    bn = render("earnings", "RAW DSE HEADLINE", "OLYMPIC", "bn", details)
    assert "৳1.72" in bn and "আগের বছর ৳1.45" in bn


def test_earnings_negative_prior_skips_percentage() -> None:
    en = render("earnings", "H", "X", "en", {"eps_current": 0.5, "eps_prior": -0.2})
    assert "vs ৳-0.2 a year earlier" in en
    assert "%" not in en.split("Earnings")[0]  # no misleading % off a negative base


def test_dividend_note_decodes_cash_stock_and_record_date() -> None:
    details = {"cash_pct": 10.0, "stock_pct": 5.0, "record_date": "2026-07-15"}
    en = render("dividend", "RAW", "GP", "en", details)
    assert "10% cash + 5% stock dividend declared" in en
    assert "record date 2026-07-15" in en


def test_no_dividend_is_stated_plainly() -> None:
    en = render("dividend", "RAW", "X", "en", {"no_dividend": True})
    assert "no dividend declared" in en


def test_rating_note_decodes_grades() -> None:
    en = render("rating", "RAW", "BRACBANK", "en", {"long_term": "AA2", "short_term": "ST-2"})
    assert "rated AA2 (long-term), ST-2 (short-term)" in en


def test_falls_back_to_headline_without_decode() -> None:
    en = render("earnings", "Board meeting outcome...", "X", "en", None)
    assert "Board meeting outcome" in en
