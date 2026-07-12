from __future__ import annotations

import datetime as dt
import json
import uuid

from bulls.core.models import SecurityMaster
from bulls.market_data.providers.us_universe_discovery import (
    PriceLiquidityObservation,
    SharesObservation,
)
from ingestion.universe_discovery import (
    DiscoveryPolicy,
    DiscoveryResult,
    evaluate_discovery_candidate,
    recent_sec_periods,
    write_discovery_artifacts,
)


def _security(name: str = "Operating Company Inc.") -> SecurityMaster:
    return SecurityMaster(
        security_id=uuid.uuid4(),
        market="US",
        symbol="TEST",
        raw_symbol="TEST",
        security_name=name,
        exchange="Nasdaq",
        cik=123,
        instrument_type="common_stock",
        is_active=True,
        is_product_eligible=True,
        source="test",
        source_file="test",
        last_seen_at=dt.datetime(2026, 7, 10, tzinfo=dt.UTC),
        updated_at=dt.datetime(2026, 7, 10, tzinfo=dt.UTC),
    )


def _shares(value: float) -> SharesObservation:
    return SharesObservation(
        cik=123,
        shares=value,
        end=dt.date(2026, 3, 31),
        accession="0000000123-26-000001",
        period="CY2026Q1I",
    )


def _price(close: float = 25.0, liquidity: float = 5.0) -> PriceLiquidityObservation:
    return PriceLiquidityObservation(
        symbol="TEST",
        price_as_of=dt.date(2026, 7, 10),
        latest_close=close,
        sessions=62,
        median_dollar_volume_mn_20d=liquidity,
        nonzero_volume_ratio=1.0,
    )


def test_candidate_selection_bands_and_excludes_below_floor_and_spacs() -> None:
    policy = DiscoveryPolicy()
    small = evaluate_discovery_candidate(
        _security(), _shares(40_000_000), _price(), policy=policy, as_of=dt.date(2026, 7, 11)
    )
    mid = evaluate_discovery_candidate(
        _security(), _shares(200_000_000), _price(), policy=policy, as_of=dt.date(2026, 7, 11)
    )
    micro = evaluate_discovery_candidate(
        _security(), _shares(5_000_000), _price(), policy=policy, as_of=dt.date(2026, 7, 11)
    )
    ultra_nano = evaluate_discovery_candidate(
        _security(), _shares(100_000), _price(), policy=policy, as_of=dt.date(2026, 7, 11)
    )
    below_floor = evaluate_discovery_candidate(
        _security(), _shares(10_000), _price(), policy=policy, as_of=dt.date(2026, 7, 11)
    )
    spac = evaluate_discovery_candidate(
        _security("Example Acquisition Corp."),
        _shares(40_000_000),
        _price(),
        policy=policy,
        as_of=dt.date(2026, 7, 11),
    )

    assert small.selected and small.band == "small_cap" and small.market_cap_mn == 1_000.0
    assert mid.selected and mid.band == "mid_cap" and mid.market_cap_mn == 5_000.0
    assert micro.selected and micro.band == "micro_cap"
    assert micro.risk_flags == ["micro_cap"]
    assert ultra_nano.selected and ultra_nano.band == "ultra_nano_cap"
    assert ultra_nano.risk_flags == ["ultra_nano_cap"]
    assert not below_floor.selected
    assert below_floor.exclusion_reasons == ["below_research_floor"]
    assert not spac.selected and "spac_or_blank_check" in spac.exclusion_reasons


def test_candidate_fails_closed_when_share_class_mapping_is_ambiguous() -> None:
    candidate = evaluate_discovery_candidate(
        _security(),
        _shares(40_000_000),
        _price(),
        policy=DiscoveryPolicy(),
        as_of=dt.date(2026, 7, 11),
        ambiguous_share_class=True,
    )

    assert not candidate.selected
    assert candidate.exclusion_reasons == ["ambiguous_share_class"]


def test_discovery_artifacts_are_versioned_mid_cap_first(tmp_path) -> None:
    selected = [
        DiscoveryResult(
            code="MID",
            security_id=str(uuid.uuid4()),
            cik=1,
            name="Mid Inc.",
            exchange="NYSE",
            instrument_type="common_stock",
            selected=True,
            band="mid_cap",
            market_cap_mn=5_000,
        ),
        DiscoveryResult(
            code="SMALL",
            security_id=str(uuid.uuid4()),
            cik=2,
            name="Small Inc.",
            exchange="Nasdaq",
            instrument_type="common_stock",
            selected=True,
            band="small_cap",
            market_cap_mn=1_000,
        ),
        DiscoveryResult(
            code="PENNY",
            security_id=str(uuid.uuid4()),
            cik=3,
            name="Penny Inc.",
            exchange="Nasdaq",
            instrument_type="common_stock",
            selected=False,
            exclusion_reasons=["price_floor"],
        ),
    ]

    artifacts = write_discovery_artifacts(
        selected,
        output_dir=tmp_path,
        policy=DiscoveryPolicy(),
        generated_at=dt.datetime(2026, 7, 11, 12, tzinfo=dt.UTC),
        periods=["CY2026Q2I", "CY2026Q1I"],
        cohort_size=100,
    )

    assert [cohort["band"] for cohort in artifacts["index"]["cohorts"]] == [
        "mid_cap",
        "small_cap",
    ]
    mid_manifest = json.loads((tmp_path / "mid-cap-2026-07-11-001.json").read_text())
    assert mid_manifest["symbols"] == ["MID"]
    assert mid_manifest["policy"]["min_market_cap_mn"] == 1.0
    assert mid_manifest["policy"]["max_market_cap_mn"] == 10_000.0
    report = json.loads((tmp_path / "discovery-report.json").read_text())
    assert report["counts"] == {
        "evaluated": 3,
        "selected": 2,
        "ultra_nano_cap": 0,
        "nano_cap": 0,
        "micro_cap": 0,
        "small_cap": 1,
        "mid_cap": 1,
        "excluded": 1,
    }
    assert report["exclusions_by_reason"] == {"price_floor": 1}


def test_penny_priced_microcaps_are_flagged_and_liquidity_gated() -> None:
    policy = DiscoveryPolicy()
    candidate = evaluate_discovery_candidate(
        _security(),
        _shares(100_000_000),
        _price(close=0.75, liquidity=0.3),
        policy=policy,
        as_of=dt.date(2026, 7, 11),
    )
    illiquid = evaluate_discovery_candidate(
        _security(),
        _shares(100_000_000),
        _price(close=0.75, liquidity=0.05),
        policy=policy,
        as_of=dt.date(2026, 7, 11),
    )

    assert candidate.selected and candidate.band == "micro_cap"
    assert candidate.risk_flags == [
        "micro_cap",
        "penny_price",
        "sub_dollar",
        "thin_liquidity",
    ]
    assert not illiquid.selected
    assert illiquid.exclusion_reasons == ["liquidity"]


def test_microcap_manifest_requires_risk_review_before_promotion(tmp_path) -> None:
    artifacts = write_discovery_artifacts(
        [
            DiscoveryResult(
                code="MICRO",
                security_id=str(uuid.uuid4()),
                cik=4,
                name="Micro Inc.",
                exchange="Nasdaq",
                instrument_type="common_stock",
                selected=True,
                band="micro_cap",
                market_cap_mn=100,
                risk_flags=["micro_cap", "penny_price"],
            )
        ],
        output_dir=tmp_path,
        policy=DiscoveryPolicy(),
        generated_at=dt.datetime(2026, 7, 11, 12, tzinfo=dt.UTC),
        periods=["CY2026Q2I"],
    )

    assert artifacts["index"]["cohorts"][0]["band"] == "micro_cap"
    manifest = json.loads((tmp_path / "micro-cap-2026-07-11-001.json").read_text())
    assert manifest["policy"]["requires_risk_review"] is True
    assert manifest["policy"]["min_adtv_mn"] == 0.25
    assert artifacts["report"]["risk_flags_by_reason"] == {
        "micro_cap": 1,
        "penny_price": 1,
    }


def test_recent_sec_periods_cross_year_boundary() -> None:
    assert recent_sec_periods(dt.date(2026, 1, 15), 4) == [
        "CY2026Q1I",
        "CY2025Q4I",
        "CY2025Q3I",
        "CY2025Q2I",
    ]
