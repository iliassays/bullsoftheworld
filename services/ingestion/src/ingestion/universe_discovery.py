"""Generate auditable small/mid-cap US cohort manifests without making symbols public.

The broad discovery estimate uses SEC share observations plus EOD price and liquidity snapshots.
Every selected symbol is subsequently revalidated by the normal per-company onboarding pipeline.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from bulls.core.config import get_settings
from bulls.core.db import get_sessionmaker
from bulls.core.markets import get_market_profile
from bulls.core.models import SecurityMaster
from bulls.market_data.providers.us_universe_discovery import (
    PriceLiquidityObservation,
    SharesObservation,
    fetch_sec_company_facts_shares,
    fetch_sec_share_frames,
    fetch_yahoo_chart_liquidity,
    fetch_yahoo_spark,
)
from ingestion.security_master import collect as refresh_security_master

MARKET = "US"
DEFAULT_COHORT_SIZE = 100
_SPAC_NAME = re.compile(r"\b(?:blank check|acquisition (?:corp(?:oration)?|company|co\.?))\b", re.I)

# Onboarding bands align with the canonical browse tiers (bulls.core.markets cap_tiers) so a
# stock's onboarding band and its user-facing size tier can never disagree. Discovery keeps its
# own finer nano/ultra-nano sub-buckets below "micro" purely for liquidity-floor policy.
_US_TIER_LOWER_BOUNDS = dict(get_market_profile(MARKET).cap_tiers)


class DiscoveryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_types: tuple[str, ...] = ("common_stock",)
    exchanges: tuple[str, ...] = (
        "Nasdaq",
        "NYSE",
        "NYSE American",
        "NYSE Arca",
        "Cboe BZX",
        "IEX",
    )
    min_market_cap_mn: float = Field(default=1.0, gt=0)
    ultra_nano_cap_upper_mn: float = Field(default=10.0, gt=0)
    nano_cap_upper_mn: float = Field(default=50.0, gt=0)
    micro_cap_upper_mn: float = Field(default=_US_TIER_LOWER_BOUNDS["small"], gt=0)
    small_cap_upper_mn: float = Field(default=_US_TIER_LOWER_BOUNDS["mid"], gt=0)
    max_market_cap_mn: float = Field(default=_US_TIER_LOWER_BOUNDS["large"], gt=0)
    min_price: float = Field(default=0.10, gt=0)
    penny_price_ceiling: float = Field(default=5.0, gt=0)
    min_median_dollar_volume_mn_20d: float = Field(default=2.0, gt=0)
    min_micro_dollar_volume_mn_20d: float = Field(default=0.25, gt=0)
    min_nano_dollar_volume_mn_20d: float = Field(default=0.10, gt=0)
    min_ultra_nano_dollar_volume_mn_20d: float = Field(default=0.05, gt=0)
    min_sessions: int = Field(default=40, ge=20, le=90)
    min_nonzero_volume_ratio: float = Field(default=0.95, ge=0, le=1)
    max_price_staleness_days: int = Field(default=10, ge=1, le=30)
    max_shares_age_days: int = Field(default=460, ge=90, le=730)
    exclude_spac_names: bool = True

    @model_validator(mode="after")
    def validate_thresholds(self) -> DiscoveryPolicy:
        caps = (
            self.min_market_cap_mn,
            self.ultra_nano_cap_upper_mn,
            self.nano_cap_upper_mn,
            self.micro_cap_upper_mn,
            self.small_cap_upper_mn,
            self.max_market_cap_mn,
        )
        if tuple(sorted(caps)) != caps or len(set(caps)) != len(caps):
            raise ValueError("market-cap thresholds must be strictly increasing")
        if self.penny_price_ceiling <= self.min_price:
            raise ValueError("penny-price ceiling must exceed the absolute price floor")
        return self


class DiscoveryResult(BaseModel):
    code: str
    security_id: str
    cik: int | None
    name: str
    exchange: str | None
    instrument_type: str
    selected: bool
    band: str | None = None
    market_cap_mn: float | None = None
    latest_close: float | None = None
    price_as_of: dt.date | None = None
    median_dollar_volume_mn_20d: float | None = None
    sessions: int = 0
    shares: float | None = None
    shares_as_of: dt.date | None = None
    shares_period: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    exclusion_reasons: list[str] = Field(default_factory=list)


def _market_cap_band(market_cap_mn: float, policy: DiscoveryPolicy) -> str | None:
    if market_cap_mn < policy.min_market_cap_mn:
        return None
    if market_cap_mn < policy.ultra_nano_cap_upper_mn:
        return "ultra_nano_cap"
    if market_cap_mn < policy.nano_cap_upper_mn:
        return "nano_cap"
    if market_cap_mn < policy.micro_cap_upper_mn:
        return "micro_cap"
    if market_cap_mn < policy.small_cap_upper_mn:
        return "small_cap"
    if market_cap_mn <= policy.max_market_cap_mn:
        return "mid_cap"
    return None


def _liquidity_floor(band: str | None, policy: DiscoveryPolicy) -> float:
    if band == "ultra_nano_cap":
        return policy.min_ultra_nano_dollar_volume_mn_20d
    if band == "nano_cap":
        return policy.min_nano_dollar_volume_mn_20d
    if band == "micro_cap":
        return policy.min_micro_dollar_volume_mn_20d
    return policy.min_median_dollar_volume_mn_20d


def recent_sec_periods(as_of: dt.date, count: int = 6) -> list[str]:
    year = as_of.year
    quarter = (as_of.month - 1) // 3 + 1
    periods: list[str] = []
    for _ in range(count):
        periods.append(f"CY{year}Q{quarter}I")
        quarter -= 1
        if quarter == 0:
            year -= 1
            quarter = 4
    return periods


def evaluate_discovery_candidate(
    security: SecurityMaster,
    shares: SharesObservation | None,
    price: PriceLiquidityObservation | None,
    *,
    policy: DiscoveryPolicy,
    as_of: dt.date,
    require_liquidity: bool = True,
    ambiguous_share_class: bool = False,
) -> DiscoveryResult:
    reasons: list[str] = []
    risk_flags: list[str] = []
    if not security.is_active or not security.is_product_eligible:
        reasons.append("listing_ineligible")
    if security.instrument_type not in policy.instrument_types:
        reasons.append("instrument_type")
    if security.exchange not in policy.exchanges:
        reasons.append("exchange")
    if security.cik is None:
        reasons.append("missing_cik")
    if policy.exclude_spac_names and _SPAC_NAME.search(security.security_name):
        reasons.append("spac_or_blank_check")
    if ambiguous_share_class:
        reasons.append("ambiguous_share_class")

    if shares is None:
        reasons.append("missing_shares")
    elif (as_of - shares.end).days < 0 or (as_of - shares.end).days > policy.max_shares_age_days:
        reasons.append("stale_shares")

    if price is None:
        reasons.append("missing_price")
    else:
        stale_days = (as_of - price.price_as_of).days
        if stale_days < 0 or stale_days > policy.max_price_staleness_days:
            reasons.append("stale_price")
        if price.latest_close < policy.min_price:
            reasons.append("price_floor")
        if price.latest_close < policy.penny_price_ceiling:
            risk_flags.append("penny_price")
        if price.latest_close < 1:
            risk_flags.append("sub_dollar")
        if price.sessions < policy.min_sessions:
            reasons.append("session_depth")

    market_cap_mn = (
        price.latest_close * shares.shares / 1e6
        if price is not None and shares is not None
        else None
    )
    band = None
    if market_cap_mn is not None:
        band = _market_cap_band(market_cap_mn, policy)
        if market_cap_mn < policy.min_market_cap_mn:
            reasons.append("below_research_floor")
        elif market_cap_mn > policy.max_market_cap_mn:
            reasons.append("large_cap")
        if band in {"ultra_nano_cap", "nano_cap", "micro_cap"}:
            risk_flags.append(band)

    liquidity_floor = _liquidity_floor(band, policy)
    if price is not None and require_liquidity:
        if price.median_dollar_volume_mn_20d is None or price.nonzero_volume_ratio is None:
            reasons.append("missing_liquidity")
        elif price.nonzero_volume_ratio < policy.min_nonzero_volume_ratio:
            reasons.append("zero_volume")
        if (
            price.median_dollar_volume_mn_20d is not None
            and price.median_dollar_volume_mn_20d < liquidity_floor
        ):
            reasons.append("liquidity")
        elif (
            price.median_dollar_volume_mn_20d is not None
            and price.median_dollar_volume_mn_20d < policy.min_median_dollar_volume_mn_20d
        ):
            risk_flags.append("thin_liquidity")

    return DiscoveryResult(
        code=security.symbol,
        security_id=str(security.security_id),
        cik=security.cik,
        name=security.security_name,
        exchange=security.exchange,
        instrument_type=security.instrument_type,
        selected=not reasons,
        band=band,
        market_cap_mn=round(market_cap_mn, 2) if market_cap_mn is not None else None,
        latest_close=price.latest_close if price else None,
        price_as_of=price.price_as_of if price else None,
        median_dollar_volume_mn_20d=(price.median_dollar_volume_mn_20d if price else None),
        sessions=price.sessions if price else 0,
        shares=shares.shares if shares else None,
        shares_as_of=shares.end if shares else None,
        shares_period=shares.period if shares else None,
        risk_flags=sorted(set(risk_flags)),
        exclusion_reasons=sorted(set(reasons)),
    )


async def _eligible_listings(limit: int | None = None) -> list[SecurityMaster]:
    sm = get_sessionmaker()
    async with sm() as session:
        stmt = (
            select(SecurityMaster)
            .where(
                SecurityMaster.market == MARKET,
                SecurityMaster.is_active.is_(True),
                SecurityMaster.is_product_eligible.is_(True),
                SecurityMaster.instrument_type == "common_stock",
            )
            .order_by(SecurityMaster.symbol)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(await session.scalars(stmt))


def _canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    temporary.replace(path)


def _onboarding_policy(policy: DiscoveryPolicy, band: str) -> dict[str, Any]:
    return {
        "allowed_instrument_types": ["common_stock"],
        "min_bars": 756,
        "min_history_days": 900,
        "max_staleness_days": policy.max_price_staleness_days,
        "min_adjusted_close_ratio": 0.98,
        "min_nonzero_volume_ratio": policy.min_nonzero_volume_ratio,
        "require_cik_for": ["common_stock"],
        "sec_filings_required_for": ["common_stock"],
        "sec_facts_required_for": ["common_stock"],
        "min_sec_filings": 4,
        "min_sec_facts": 12,
        "require_analytics": True,
        "require_13f": False,
        "min_market_cap_mn": policy.min_market_cap_mn,
        "max_market_cap_mn": policy.max_market_cap_mn,
        "min_adtv_mn": _liquidity_floor(band, policy),
        "min_price": policy.min_price,
        "requires_risk_review": band in {"ultra_nano_cap", "nano_cap", "micro_cap"},
    }


def write_discovery_artifacts(
    results: list[DiscoveryResult],
    *,
    output_dir: Path,
    policy: DiscoveryPolicy,
    generated_at: dt.datetime,
    periods: list[str],
    cohort_size: int = DEFAULT_COHORT_SIZE,
    source_observations: dict[str, int] | None = None,
) -> dict[str, Any]:
    selected = [row for row in results if row.selected]
    exclusions = Counter(reason for row in results for reason in row.exclusion_reasons)
    report_payload = {
        "schema_version": 1,
        "generated_at": generated_at.isoformat(),
        "as_of_date": generated_at.date().isoformat(),
        "market": MARKET,
        "purpose": "private universe discovery; not a public index or recommendation",
        "sources": {
            "identity": "Nasdaq Trader symbol directory + SEC ticker/exchange mapping",
            "shares": "SEC XBRL shares frames with Company Facts fallback",
            "price_liquidity": "Yahoo batch EOD spark bootstrap adapter",
            "sec_periods": periods,
        },
        "source_observations": source_observations or {},
        "policy": policy.model_dump(mode="json"),
        "counts": {
            "evaluated": len(results),
            "selected": len(selected),
            "ultra_nano_cap": sum(row.band == "ultra_nano_cap" for row in selected),
            "nano_cap": sum(row.band == "nano_cap" for row in selected),
            "micro_cap": sum(row.band == "micro_cap" for row in selected),
            "small_cap": sum(row.band == "small_cap" for row in selected),
            "mid_cap": sum(row.band == "mid_cap" for row in selected),
            "excluded": len(results) - len(selected),
        },
        "risk_flags_by_reason": dict(
            sorted(Counter(flag for row in selected for flag in row.risk_flags).items())
        ),
        "exclusions_by_reason": dict(sorted(exclusions.items())),
        "selected": [row.model_dump(mode="json") for row in selected],
        "excluded": [row.model_dump(mode="json") for row in results if not row.selected],
    }
    report_hash = _canonical_hash(report_payload)
    report_payload["snapshot_sha256"] = report_hash
    _write_json(output_dir / "discovery-report.json", report_payload)

    cohort_records: list[dict[str, Any]] = []
    version = generated_at.date().isoformat()
    for band in ("mid_cap", "small_cap", "micro_cap", "nano_cap", "ultra_nano_cap"):
        band_rows = sorted(
            (row for row in selected if row.band == band),
            key=lambda row: (-(row.market_cap_mn or 0), row.code),
        )
        for index in range(0, len(band_rows), cohort_size):
            part = index // cohort_size + 1
            rows = band_rows[index : index + cohort_size]
            filename = f"{band.replace('_', '-')}-{version}-{part:03d}.json"
            payload = {
                "schema_version": 1,
                "name": f"bullsofwallst-{band}-{version}-{part:03d}",
                "version": f"{version}.{part:03d}",
                "market": MARKET,
                "backfill_years": 10,
                "description": (
                    f"Generated private {band.replace('_', ' ')} research cohort from discovery "
                    f"snapshot {report_hash[:12]}; not an index-membership or investment claim."
                ),
                "policy": _onboarding_policy(policy, band),
                "symbols": [row.code for row in rows],
            }
            _write_json(output_dir / filename, payload)
            cohort_records.append(
                {
                    "band": band,
                    "file": filename,
                    "count": len(rows),
                    "manifest_sha256": _canonical_hash(payload),
                }
            )

    index_payload = {
        "schema_version": 1,
        "generated_at": generated_at.isoformat(),
        "market": MARKET,
        "discovery_snapshot_sha256": report_hash,
        "cohort_size": cohort_size,
        "cohorts": cohort_records,
    }
    _write_json(output_dir / "manifest-index.json", index_payload)
    return {"report": report_payload, "index": index_payload}


async def discover(
    *,
    output_dir: Path,
    policy: DiscoveryPolicy,
    refresh_master: bool = True,
    limit_listings: int | None = None,
    cohort_size: int = DEFAULT_COHORT_SIZE,
    max_companyfacts_fallback: int = 2_000,
) -> dict[str, Any]:
    if refresh_master:
        await refresh_security_master(MARKET)
    listings = await _eligible_listings(limit_listings)
    as_of = dt.datetime.now(dt.UTC)
    periods = recent_sec_periods(as_of.date())
    user_agent = f"BullsOfTheWorld/0.1 universe-discovery {get_settings().sec_contact_email}"
    shares_by_cik, spark_prices = await asyncio.gather(
        fetch_sec_share_frames(periods, user_agent=user_agent),
        fetch_yahoo_spark(listing.symbol for listing in listings),
    )
    cik_counts = Counter(listing.cik for listing in listings if listing.cik is not None)
    ambiguous_ciks = {cik for cik, count in cik_counts.items() if count > 1}
    fallback_ciks = sorted(
        {
            listing.cik
            for listing in listings
            if listing.cik is not None
            and listing.cik not in shares_by_cik
            and listing.cik not in ambiguous_ciks
            and listing.exchange in policy.exchanges
            and not (policy.exclude_spac_names and _SPAC_NAME.search(listing.security_name))
            and (price := spark_prices.get(listing.symbol)) is not None
            and price.latest_close >= policy.min_price
            and price.sessions >= policy.min_sessions
            and 0 <= (as_of.date() - price.price_as_of).days <= policy.max_price_staleness_days
        }
    )
    if len(fallback_ciks) > max_companyfacts_fallback:
        raise RuntimeError(
            f"Company Facts fallback needs {len(fallback_ciks)} CIKs, above the explicit "
            f"limit of {max_companyfacts_fallback}"
        )
    fallback_shares = await fetch_sec_company_facts_shares(
        fallback_ciks,
        user_agent=user_agent,
    )
    shares_by_cik = {**fallback_shares, **shares_by_cik}
    preliminary = [
        evaluate_discovery_candidate(
            listing,
            shares_by_cik.get(listing.cik) if listing.cik is not None else None,
            spark_prices.get(listing.symbol),
            policy=policy,
            as_of=as_of.date(),
            require_liquidity=False,
            ambiguous_share_class=(listing.cik is not None and listing.cik in ambiguous_ciks),
        )
        for listing in listings
    ]
    liquidity_codes = [
        row.code
        for row in preliminary
        if row.selected
        and row.band in {"ultra_nano_cap", "nano_cap", "micro_cap", "small_cap", "mid_cap"}
    ]
    chart_prices = await fetch_yahoo_chart_liquidity(liquidity_codes)
    prices_by_code = {**spark_prices, **chart_prices}
    results = [
        evaluate_discovery_candidate(
            listing,
            shares_by_cik.get(listing.cik) if listing.cik is not None else None,
            prices_by_code.get(listing.symbol),
            policy=policy,
            as_of=as_of.date(),
            require_liquidity=listing.symbol in liquidity_codes,
            ambiguous_share_class=(listing.cik is not None and listing.cik in ambiguous_ciks),
        )
        for listing in listings
    ]
    artifacts = write_discovery_artifacts(
        results,
        output_dir=output_dir,
        policy=policy,
        generated_at=as_of,
        periods=periods,
        cohort_size=cohort_size,
        source_observations={
            "frame_shares": len(shares_by_cik) - len(fallback_shares),
            "companyfacts_fallback_requested": len(fallback_ciks),
            "companyfacts_fallback_resolved": len(fallback_shares),
            "batch_prices": len(spark_prices),
            "candidate_liquidity_histories": len(chart_prices),
        },
    )
    return {
        "output_dir": str(output_dir),
        **artifacts["report"]["counts"],
        "cohorts": len(artifacts["index"]["cohorts"]),
        "snapshot_sha256": artifacts["report"]["snapshot_sha256"],
        "companyfacts_fallback_requested": len(fallback_ciks),
        "companyfacts_fallback_resolved": len(fallback_shares),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover private US small/mid-cap cohorts")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--skip-security-master-refresh", action="store_true")
    parser.add_argument("--limit-listings", type=int, default=None)
    parser.add_argument("--cohort-size", type=int, default=DEFAULT_COHORT_SIZE)
    parser.add_argument("--max-companyfacts-fallback", type=int, default=2_000)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    today = dt.datetime.now(dt.UTC).date().isoformat()
    output_dir = args.output_dir or Path("var/us-universe") / today
    if args.cohort_size < 10 or args.cohort_size > 250:
        raise ValueError("cohort size must be between 10 and 250")
    if args.max_companyfacts_fallback < 0:
        raise ValueError("max Company Facts fallback must not be negative")
    result = asyncio.run(
        discover(
            output_dir=output_dir,
            policy=DiscoveryPolicy(),
            refresh_master=not args.skip_security_master_refresh,
            limit_listings=args.limit_listings,
            cohort_size=args.cohort_size,
            max_companyfacts_fallback=args.max_companyfacts_fallback,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
