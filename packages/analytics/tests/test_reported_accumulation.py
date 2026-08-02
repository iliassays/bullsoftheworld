from bulls.analytics.reported_accumulation import (
    ReportedAccumulationInput,
    assess_reported_accumulation,
)


def test_dse_requires_near_low_and_a_real_reported_stake_increase() -> None:
    qualified = assess_reported_accumulation(
        ReportedAccumulationInput(
            market="DSE",
            pct_above_52w_low=4.2,
            institutional_change_pp=0.4,
        )
    )
    outside_zone = assess_reported_accumulation(
        ReportedAccumulationInput(
            market="DSE",
            pct_above_52w_low=18.0,
            institutional_change_pp=2.0,
        )
    )
    unchanged = assess_reported_accumulation(
        ReportedAccumulationInput(
            market="DSE",
            pct_above_52w_low=4.2,
            institutional_change_pp=0.0,
        )
    )

    assert qualified.eligible is True
    assert qualified.strength == "meaningful"
    assert outside_zone.reason == "outside_yearly_low_zone"
    assert unchanged.reason == "no_reported_stake_increase"


def test_us_requires_positive_manager_breadth_and_net_reported_shares() -> None:
    qualified = assess_reported_accumulation(
        ReportedAccumulationInput(
            market="US",
            pct_above_52w_low=7.0,
            adding_managers=9,
            reducing_managers=3,
            net_share_change=50_000,
        )
    )
    share_outlier_without_breadth = assess_reported_accumulation(
        ReportedAccumulationInput(
            market="US",
            pct_above_52w_low=7.0,
            adding_managers=2,
            reducing_managers=3,
            net_share_change=9_000_000_000,
        )
    )
    positive_breadth_without_positive_shares = assess_reported_accumulation(
        ReportedAccumulationInput(
            market="US",
            pct_above_52w_low=7.0,
            adding_managers=9,
            reducing_managers=3,
            net_share_change=-1,
        )
    )

    assert qualified.eligible is True
    assert qualified.strength == "broad"
    assert qualified.net_manager_breadth_pct == 50
    assert share_outlier_without_breadth.eligible is False
    assert positive_breadth_without_positive_shares.reason == "net_reported_shares_not_higher"


def test_missing_or_negative_distance_never_qualifies() -> None:
    for distance in (None, -0.1):
        assessment = assess_reported_accumulation(
            ReportedAccumulationInput(
                market="DSE",
                pct_above_52w_low=distance,
                institutional_change_pp=1.0,
            )
        )
        assert assessment.eligible is False
