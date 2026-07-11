"""Stock Scorecard + Red Flags — deterministic, dimensions-only (no composite), omit-over-mislead."""

from __future__ import annotations

from bulls.analytics.scorecard import build_red_flags, build_scorecard


def test_high_quality_uptrend():
    sc = build_scorecard(
        code="GP",
        as_of_date="2026-06-30",
        above_sma_200=True,
        above_sma_50=True,
        mom_12_1=34,
        roe=22,
        pe_vs_sector=1.3,
        pe_ratio=18,
        dividend_yield=6.2,
        rsi_14=58,
        mom_6_1=9,
    )
    by = {d.key: d for d in sc.dimensions}
    assert by["quality"].score == 10
    assert by["trend"].score >= 8
    assert by["value"].score <= 4  # pricier than sector → low value score (= expensive, not "bad")
    assert by["income"].score == 8
    # No composite/overall field exists — dimensions only.
    assert not hasattr(sc, "overall")


def test_no_composite_only_dimensions():
    sc = build_scorecard(code="X", as_of_date="2026-06-30", roe=10, pe_vs_sector=0.8)
    keys = {d.key for d in sc.dimensions}
    assert keys == {"quality", "value"}  # trend/income/momentum omitted, never zero-filled


def test_value_low_score_is_expensive_not_bad():
    cheap = build_scorecard(code="A", as_of_date="d", pe_vs_sector=0.6)
    pricey = build_scorecard(code="B", as_of_date="d", pe_vs_sector=1.6)
    assert cheap.dimensions[0].score > pricey.dimensions[0].score


def test_income_omitted_when_no_dividend():
    sc = build_scorecard(code="X", as_of_date="d", roe=12, dividend_yield=0)
    assert all(d.key != "income" for d in sc.dimensions)


def test_red_flags_fire():
    rf = build_red_flags(
        code="XYZ",
        category="Z",
        adtv_mn=0.5,
        roe=-3,
        dividend_yield=0,
        free_float_cap_mn=40,
        today_change_pct=9.9,
    )
    keys = {f.key for f in rf.flags}
    assert keys == {"z_category", "thin", "lossmaking", "tiny_float", "circuit"}
    assert rf.clean is False


def test_red_flags_clean():
    rf = build_red_flags(
        code="GP", category="A", adtv_mn=120, roe=22, dividend_yield=6.2, free_float_cap_mn=5000
    )
    assert rf.flags == []
    assert rf.clean is True


def test_red_flags_bilingual():
    rf = build_red_flags(code="XYZ", locale="bn", category="Z", roe=-1)
    labels = {f.label for f in rf.flags}
    assert "Z-ক্যাটাগরি" in labels
    assert "লোকসানে" in labels
    assert "কিনবেন না" in rf.note
