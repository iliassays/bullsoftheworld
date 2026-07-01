from bulls.analytics import build_investor_lens


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
    assert result.disclaimer.startswith("Investor Lens")
