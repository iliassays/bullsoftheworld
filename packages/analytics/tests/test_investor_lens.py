from bulls.analytics import build_investor_lens, dividend_score


def _by_key(result):
    return {lens.key: lens for lens in result.lenses}


def test_investor_lens_separates_value_from_risk():
    result = build_investor_lens(
        code="GP",
        as_of_date="2026-06-30",
        category="Z",
        pe_ratio=9.0,
        pb_ratio=0.9,
        pe_vs_sector=0.65,
        roe=18.0,
        eps_growth_yoy=12.0,
        dividend_yield=4.5,
        above_sma_50=True,
        above_sma_200=True,
        mom_12_1=32.0,
        rsi_14=58.0,
        relative_volume=1.8,
        institute_pct=24.0,
        foreign_pct=3.0,
        institute_delta=1.4,
        foreign_delta=0.9,
        cmf_20=0.15,
        adtv_mn=1.5,
        free_float_cap_mn=80.0,
        volatility=82.0,
        today_change_pct=9.8,
    )

    lenses = _by_key(result)
    assert lenses["graham_value"].verdict == "supportive"
    assert lenses["buffett_quality"].verdict == "supportive"
    assert lenses["taleb_risk"].verdict == "caution"
    assert "recommendation" in result.disclaimer


def test_investor_lens_handles_thin_missing_inputs():
    result = build_investor_lens(
        code="ABC",
        as_of_date="2026-06-30",
        locale="bn",
        category="A",
        adtv_mn=25.0,
    )

    lenses = _by_key(result)
    assert lenses["graham_value"].verdict == "thin_data"
    assert lenses["smart_money"].verdict == "thin_data"
    assert lenses["taleb_risk"].score is not None
    assert "অনুপস্থিত পরীক্ষা" in result.disclaimer


def test_us_lens_uses_us_currency_and_omits_dse_only_checks():
    result = build_investor_lens(
        code="AAPL",
        as_of_date="2026-07-10",
        market="US",
        locale="en",
        adtv_mn=5000,
        volatility=22,
        today_change_pct=1.2,
        nearest_support=201.25,
        nearest_resistance=220.5,
        above_sma_50=True,
    )

    lenses = _by_key(result)
    technical = lenses["technical_trader"]
    risk = lenses["taleb_risk"]
    levels = next(check for check in technical.checks if check.label == "Support / resistance")
    assert levels.actual == "$201.25 / $220.50"
    assert all(check.label != "Category" for check in risk.checks)
    assert "$" in next(check for check in risk.checks if check.label == "Liquidity (ADTV)").actual
    assert "DSE" not in result.disclaimer


def test_token_dividend_yield_cannot_look_like_strong_income():
    assert dividend_score(dividend_yield=0.3, roe=30, eps_growth_yoy=20) <= 4
