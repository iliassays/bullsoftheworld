import pytest

from bulls.analytics.dse_fund_allocator import (
    DseFundPolicy,
    DseSleeveIntent,
    allocate_dse_fund_targets,
)


def _sleeve(
    key: str,
    *,
    priority: int,
    budget: float,
    targets: tuple[tuple[str, float], ...],
) -> DseSleeveIntent:
    return DseSleeveIntent(
        key=key,
        priority=priority,
        budget_weight=budget,
        target_weights=targets,
    )


def test_dse_fund_allocator_combines_sleeves_under_shared_limits() -> None:
    target = allocate_dse_fund_targets(
        sleeves=[
            _sleeve(
                "quality_core",
                priority=10,
                budget=0.60,
                targets=(("BRACBANK", 0.20), ("BXPHARMA", 0.20), ("SQURPHARMA", 0.20)),
            ),
            _sleeve(
                "reversal",
                priority=20,
                budget=0.20,
                targets=(("GP", 0.10), ("ROBI", 0.10)),
            ),
        ],
        sectors={
            "BRACBANK": "Bank",
            "BXPHARMA": "Pharmaceuticals",
            "SQURPHARMA": "Pharmaceuticals",
            "GP": "Telecommunication",
            "ROBI": "Telecommunication",
        },
        policy=DseFundPolicy(
            maximum_gross_weight=0.80,
            minimum_cash_weight=0.20,
            maximum_name_weight=0.15,
            maximum_sector_weight=0.25,
        ),
    )

    weights = dict(target.target_weights)
    assert target.gross_weight <= 0.80
    assert target.cash_weight >= 0.20
    assert max(weights.values()) <= 0.15
    assert weights["BXPHARMA"] + weights["SQURPHARMA"] <= 0.25
    assert target.sleeve_evidence_states == (
        ("quality_core", "diagnostic"),
        ("reversal", "diagnostic"),
    )
    assert target.capital_action == "none"


def test_dse_fund_allocator_caps_one_name_across_overlapping_sleeves() -> None:
    target = allocate_dse_fund_targets(
        sleeves=[
            _sleeve(
                "quality_core",
                priority=10,
                budget=0.40,
                targets=(("BRACBANK", 0.20),),
            ),
            _sleeve(
                "reversal",
                priority=20,
                budget=0.20,
                targets=(("BRACBANK", 0.15),),
            ),
        ],
        sectors={"BRACBANK": "Bank"},
        policy=DseFundPolicy(maximum_name_weight=0.12),
    )

    assert dict(target.target_weights)["BRACBANK"] == pytest.approx(0.12)
    assert sum(
        weight for _sleeve_key, code, weight in target.sleeve_contributions if code == "BRACBANK"
    ) == pytest.approx(0.12)
    assert any(
        item.code == "BRACBANK" and item.rule == "fund_name_limit" for item in target.interventions
    )


def test_dse_fund_allocator_rejects_budgets_above_fund_mandate() -> None:
    with pytest.raises(ValueError, match="budgets exceed"):
        allocate_dse_fund_targets(
            sleeves=[
                _sleeve("quality_core", priority=10, budget=0.70, targets=()),
                _sleeve("reversal", priority=20, budget=0.20, targets=()),
            ],
            sectors={},
        )


def test_dse_fund_allocator_is_independent_of_input_sleeve_order() -> None:
    quality = _sleeve(
        "quality_core",
        priority=10,
        budget=0.50,
        targets=(("BRACBANK", 0.30), ("BXPHARMA", 0.30)),
    )
    reversal = _sleeve(
        "reversal",
        priority=20,
        budget=0.20,
        targets=(("BRACBANK", 0.10), ("GP", 0.10)),
    )
    kwargs = {
        "sectors": {
            "BRACBANK": "Bank",
            "BXPHARMA": "Pharmaceuticals",
            "GP": "Telecommunication",
        },
        "policy": DseFundPolicy(maximum_name_weight=0.20),
    }

    forward = allocate_dse_fund_targets(sleeves=[quality, reversal], **kwargs)
    reverse = allocate_dse_fund_targets(sleeves=[reversal, quality], **kwargs)

    assert forward == reverse
