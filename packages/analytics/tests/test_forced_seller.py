from bulls.analytics.forced_seller import (
    ForcedSellerDatasetCoverage,
    assess_forced_seller_readiness,
)


def test_system_b_fails_closed_when_official_history_is_missing() -> None:
    readiness = assess_forced_seller_readiness(ForcedSellerDatasetCoverage())

    assert readiness.status == "data_blocked"
    assert "authoritative historical spin-off/distribution events" in readiness.missing_datasets
    assert "will not proxy" in readiness.statement


def test_system_b_is_ready_only_when_every_contract_is_complete() -> None:
    readiness = assess_forced_seller_readiness(
        ForcedSellerDatasetCoverage(
            corporate_action_history_complete=True,
            effective_timestamps_complete=True,
            parent_holder_history_complete=True,
            post_bankruptcy_distributions_complete=True,
            point_in_time_fundamentals_complete=True,
            inactive_listing_history_complete=True,
            adjusted_price_history_complete=True,
        )
    )

    assert readiness.status == "ready"
    assert readiness.missing_datasets == []
