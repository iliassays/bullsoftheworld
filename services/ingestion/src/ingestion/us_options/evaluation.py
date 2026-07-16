"""Reproducible one-year feasibility evaluation for Cboe Option Sentiment.

This module performs descriptive data-quality evaluation only. It does not generate a trading
signal, run a strategy backtest, or publish customer-facing options evidence.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import random
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

import polars as pl
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bulls.core.config import Settings, get_settings
from bulls.core.markets import US_VERIFIED_CALENDAR_YEARS
from bulls.core.models import ResearchDatasetEvaluation, ResearchDatasetSnapshot
from bulls.market_data.calendar import is_trading_day
from bulls.market_data.options.cboe_sentiment import CBOE_OPTION_SENTIMENT_SCHEMA_VERSION
from ingestion.us_options.pipeline import (
    DATASET_KEY,
    MARKET,
    TENANT_ID,
    _bind_shared_research_scope,
    _entitlement,
)
from ingestion.us_options.quality import IDENTITY_VERSION, NORMALIZATION_VERSION
from ingestion.us_options.storage import ImmutableObjectStore, object_store

METHODOLOGY_VERSION = "cboe-option-sentiment-feasibility-v1"
MAX_NORMALIZED_PARQUET_BYTES = 256 * 1024 * 1024
MIN_CALENDAR_COVERAGE = 0.98
MIN_ONE_YEAR_SESSIONS = 240
MAX_DAILY_DISTRIBUTION_SAMPLE_ROWS = 2_000
MAX_METRIC_RESERVOIR_VALUES = 50_000
_DISTRIBUTION_FIELDS = (
    "total_volume",
    "avg_total_volume",
    "total_trades",
    "avg_call_size",
    "avg_put_size",
    "underlying_volume",
    "call_premium",
    "put_premium",
    "spot_close",
    "net_option_delta",
    "oi_calls",
    "oi_puts",
    "iv30",
    "hv20",
    "iv90",
    "vega_total",
    "cust_volume",
    "firm_volume",
    "mkt_mkr_volume",
    "implied_borrow",
    "norm_25d_skew_30",
    "directional_pct",
    "put_call_volume_ratio",
    "directional_premium_balance",
    "iv30_minus_hv20",
    "iv90_minus_iv30",
    "option_to_stock_volume_ratio",
    "dtx1_share",
    "small_lot_share",
)
_DERIVED_DISTRIBUTION_FIELDS = {
    "put_call_volume_ratio",
    "directional_premium_balance",
    "iv30_minus_hv20",
    "iv90_minus_iv30",
    "option_to_stock_volume_ratio",
    "dtx1_share",
    "small_lot_share",
}
_CRITICAL_FIELDS = (
    "trade_date",
    "underlying_symbol",
    "underlying_security_type",
    "total_volume",
    "total_trades",
    "underlying_volume",
    "spot_close",
    "split_adj_close",
    "net_option_delta",
    "directional_pct",
)


class DistributionSummary(BaseModel):
    count: int = Field(ge=0)
    null_count: int = Field(ge=0)
    quantile_sample_count: int = Field(default=0, ge=0)
    quantiles_are_approximate: bool = False
    mean: float | None = None
    minimum: float | None = None
    p05: float | None = None
    p25: float | None = None
    median: float | None = None
    p75: float | None = None
    p95: float | None = None
    maximum: float | None = None


class EvaluationGate(BaseModel):
    name: str
    passed: bool
    observed: str
    requirement: str


class OptionSentimentFeasibilityReport(BaseModel):
    methodology_version: str = METHODOLOGY_VERSION
    generated_at: dt.datetime
    tenant_id: Literal["bullsofwallst"] = TENANT_ID
    market: Literal["US"] = MARKET
    dataset_key: Literal["cboe_option_sentiment"] = DATASET_KEY
    start_date: dt.date
    end_date: dt.date
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal[
        "insufficient_data",
        "quality_review_required",
        "ready_for_phase_b_review",
    ]
    expected_session_count: int = Field(ge=0)
    canonical_session_count: int = Field(ge=0)
    calendar_coverage: float = Field(ge=0, le=1)
    missing_sessions: list[dt.date]
    rejected_delivery_count: int = Field(ge=0)
    ignored_noncomplete_delivery_count: int = Field(ge=0)
    superseded_revision_count: int = Field(ge=0)
    total_row_count: int = Field(ge=0)
    daily_row_count: DistributionSummary
    security_type_counts: dict[str, int]
    identity_status_counts: dict[str, int]
    stock_identity_coverage: float = Field(ge=0, le=1)
    unmatched_stock_symbols: list[dict[str, int | str]]
    null_rates: dict[str, float]
    metric_distributions: dict[str, DistributionSummary]
    distribution_sampling_method: str
    delivery_modes: dict[str, int]
    subscription_delivery_lag_hours: DistributionSummary | None
    split_adjustment_row_count: int = Field(ge=0)
    split_adjustment_underlyings: list[str]
    low_breadth_sessions: list[dt.date]
    schema_versions: list[str]
    normalization_versions: list[str]
    identity_versions: list[str]
    gates: list[EvaluationGate]
    findings: list[str]


@dataclass(frozen=True, slots=True)
class EvaluationDelivery:
    snapshot_id: str
    trade_date: dt.date
    effective_at: dt.datetime
    known_at: dt.datetime
    delivery_mode: str
    frame: pl.DataFrame


def expected_us_sessions(start_date: dt.date, end_date: dt.date) -> list[dt.date]:
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")
    years = set(range(start_date.year, end_date.year + 1))
    unsupported = years - US_VERIFIED_CALENDAR_YEARS
    if unsupported:
        raise ValueError(
            "US options evaluation requires verified exchange calendars for years: "
            + ", ".join(str(year) for year in sorted(unsupported))
        )
    sessions: list[dt.date] = []
    current = start_date
    while current <= end_date:
        if is_trading_day(current, market=MARKET):
            sessions.append(current)
        current += dt.timedelta(days=1)
    return sessions


def _float(value: Any) -> float | None:
    return None if value is None else float(value)


def _distribution(frame: pl.DataFrame, field: str) -> DistributionSummary:
    if field not in frame.columns:
        return DistributionSummary(count=0, null_count=frame.height)
    value = pl.col(field).cast(pl.Float64, strict=False)
    result = frame.select(
        value.count().alias("count"),
        value.null_count().alias("null_count"),
        value.mean().alias("mean"),
        value.min().alias("minimum"),
        value.quantile(0.05, interpolation="linear").alias("p05"),
        value.quantile(0.25, interpolation="linear").alias("p25"),
        value.median().alias("median"),
        value.quantile(0.75, interpolation="linear").alias("p75"),
        value.quantile(0.95, interpolation="linear").alias("p95"),
        value.max().alias("maximum"),
    ).row(0, named=True)
    return DistributionSummary(
        count=int(result["count"]),
        null_count=int(result["null_count"]),
        quantile_sample_count=int(result["count"]),
        quantiles_are_approximate=False,
        mean=_float(result["mean"]),
        minimum=_float(result["minimum"]),
        p05=_float(result["p05"]),
        p25=_float(result["p25"]),
        median=_float(result["median"]),
        p75=_float(result["p75"]),
        p95=_float(result["p95"]),
        maximum=_float(result["maximum"]),
    )


def _sample_quantile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


@dataclass(slots=True)
class _MetricAccumulator:
    name: str
    count: int = 0
    null_count: int = 0
    total: float = 0.0
    minimum: float | None = None
    maximum: float | None = None
    sample_seen: int = 0
    samples: list[float] = field(default_factory=list)
    _random: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        seed = int.from_bytes(hashlib.sha256(self.name.encode()).digest()[:8])
        self._random = random.Random(seed)

    def add_exact(
        self,
        *,
        count: int,
        null_count: int,
        total: float | None,
        minimum: float | None,
        maximum: float | None,
    ) -> None:
        self.count += count
        self.null_count += null_count
        if total is not None:
            self.total += total
        if minimum is not None:
            self.minimum = minimum if self.minimum is None else min(self.minimum, minimum)
        if maximum is not None:
            self.maximum = maximum if self.maximum is None else max(self.maximum, maximum)

    def add_samples(self, values: Iterable[float | int | None]) -> None:
        for value in values:
            if value is None:
                continue
            numeric = float(value)
            self.sample_seen += 1
            if len(self.samples) < MAX_METRIC_RESERVOIR_VALUES:
                self.samples.append(numeric)
                continue
            replacement = self._random.randrange(self.sample_seen)
            if replacement < MAX_METRIC_RESERVOIR_VALUES:
                self.samples[replacement] = numeric

    def summary(self) -> DistributionSummary:
        sample_count = len(self.samples)
        return DistributionSummary(
            count=self.count,
            null_count=self.null_count,
            quantile_sample_count=sample_count,
            quantiles_are_approximate=sample_count < self.count,
            mean=self.total / self.count if self.count else None,
            minimum=self.minimum,
            p05=_sample_quantile(self.samples, 0.05),
            p25=_sample_quantile(self.samples, 0.25),
            median=_sample_quantile(self.samples, 0.5),
            p75=_sample_quantile(self.samples, 0.75),
            p95=_sample_quantile(self.samples, 0.95),
            maximum=self.maximum,
        )


def _accumulate_metrics(
    frame: pl.DataFrame,
    accumulators: dict[str, _MetricAccumulator],
    *,
    sample_seed: int,
) -> None:
    expressions: list[pl.Expr] = []
    for metric in _DISTRIBUTION_FIELDS:
        value = pl.col(metric).cast(pl.Float64, strict=False)
        expressions.extend(
            (
                value.count().alias(f"{metric}__count"),
                value.null_count().alias(f"{metric}__null_count"),
                value.sum().alias(f"{metric}__sum"),
                value.min().alias(f"{metric}__minimum"),
                value.max().alias(f"{metric}__maximum"),
            )
        )
    exact = frame.select(expressions).row(0, named=True)
    for metric, accumulator in accumulators.items():
        accumulator.add_exact(
            count=int(exact[f"{metric}__count"]),
            null_count=int(exact[f"{metric}__null_count"]),
            total=_float(exact[f"{metric}__sum"]),
            minimum=_float(exact[f"{metric}__minimum"]),
            maximum=_float(exact[f"{metric}__maximum"]),
        )

    sampled = frame.select(_DISTRIBUTION_FIELDS).sample(
        n=min(frame.height, MAX_DAILY_DISTRIBUTION_SAMPLE_ROWS),
        seed=sample_seed,
        shuffle=True,
    )
    for metric, accumulator in accumulators.items():
        accumulator.add_samples(
            sampled.get_column(metric).cast(pl.Float64, strict=False).to_list()
        )


def _counts(frame: pl.DataFrame, field: str) -> dict[str, int]:
    if frame.is_empty():
        return {}
    return {
        str(row[field]): int(row["len"])
        for row in frame.group_by(field).len().sort(field).iter_rows(named=True)
    }


def _derived_columns(frame: pl.DataFrame) -> pl.DataFrame:
    size_fields = (
        "size1",
        "size2_10",
        "size11_100",
        "size101_500",
        "size501_1000",
        "size1001up",
    )
    all_sizes_available = pl.all_horizontal(
        *(pl.col(field).is_not_null() for field in size_fields)
    )
    positive_volume = pl.col("total_volume") > 0
    return frame.with_columns(
        pl.when(pl.col("call_volume") > 0)
        .then(pl.col("put_volume") / pl.col("call_volume"))
        .otherwise(None)
        .alias("put_call_volume_ratio"),
        (
            pl.col("call_premium_bought")
            + pl.col("put_premium_sold")
            - pl.col("call_premium_sold")
            - pl.col("put_premium_bought")
        ).alias("directional_premium_balance"),
        (pl.col("iv30") - pl.col("hv20")).alias("iv30_minus_hv20"),
        (pl.col("iv90") - pl.col("iv30")).alias("iv90_minus_iv30"),
        pl.when(pl.col("underlying_volume") > 0)
        .then(pl.col("total_volume") / pl.col("underlying_volume"))
        .otherwise(None)
        .alias("option_to_stock_volume_ratio"),
        pl.when(positive_volume)
        .then(pl.col("dtx1") / pl.col("total_volume"))
        .otherwise(None)
        .alias("dtx1_share"),
        pl.when(all_sizes_available & positive_volume)
        .then((pl.col("size1") + pl.col("size2_10")) / pl.col("total_volume"))
        .otherwise(None)
        .alias("small_lot_share"),
    )


def _prepare_frame(payload: bytes, *, trade_date: dt.date) -> pl.DataFrame:
    frame = pl.read_parquet(io.BytesIO(payload))
    required = {
        "canonical_code",
        "identity_status",
        "trade_date",
        "underlying_symbol",
        "underlying_security_type",
        *(
            field
            for field in _DISTRIBUTION_FIELDS
            if field not in _DERIVED_DISTRIBUTION_FIELDS
        ),
        "split_adj_close",
        "call_volume",
        "put_volume",
        "call_premium_bought",
        "call_premium_sold",
        "put_premium_bought",
        "put_premium_sold",
        "dtx1",
        "size1",
        "size2_10",
        "size11_100",
        "size101_500",
        "size501_1000",
        "size1001up",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"normalized Option Sentiment Parquet is missing: {missing}")
    frame = frame.select(sorted(required)).with_columns(
        pl.col("trade_date").cast(pl.String).str.to_date(strict=True)
    )
    dates = frame.get_column("trade_date").unique().to_list()
    if dates != [trade_date]:
        raise ValueError(
            f"normalized Option Sentiment date mismatch: snapshot={trade_date}, rows={dates}"
        )
    return _derived_columns(frame)


def _input_fingerprint(snapshots: list[ResearchDatasetSnapshot]) -> str:
    payload = [
        {
            "id": str(snapshot.id),
            "trade_date": snapshot.trade_date.isoformat(),
            "status": snapshot.status,
            "completeness": snapshot.completeness,
            "source_revision": snapshot.source_revision,
            "normalized_sha256": snapshot.normalized_sha256,
            "dataset_fingerprint": snapshot.dataset_fingerprint,
        }
        for snapshot in sorted(
            snapshots,
            key=lambda item: (
                item.trade_date,
                item.completeness,
                item.source_revision,
                str(item.id),
            ),
        )
    ]
    encoded = json.dumps(
        {
            "methodology_version": METHODOLOGY_VERSION,
            "snapshots": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _canonical_snapshots(
    snapshots: list[ResearchDatasetSnapshot],
) -> tuple[list[ResearchDatasetSnapshot], int, int, int]:
    accepted_complete: dict[dt.date, list[ResearchDatasetSnapshot]] = {}
    rejected = ignored = 0
    for snapshot in snapshots:
        if snapshot.completeness != "complete":
            ignored += 1
            continue
        if snapshot.status != "accepted":
            rejected += 1
            continue
        accepted_complete.setdefault(snapshot.trade_date, []).append(snapshot)

    canonical: list[ResearchDatasetSnapshot] = []
    superseded = 0
    for trade_date in sorted(accepted_complete):
        revisions = accepted_complete[trade_date]
        revisions.sort(
            key=lambda item: (item.known_at, item.ingested_at, str(item.id)),
            reverse=True,
        )
        canonical.append(revisions[0])
        superseded += len(revisions) - 1
    return canonical, rejected, ignored, superseded


def evaluate_option_sentiment(
    deliveries: Iterable[EvaluationDelivery],
    *,
    start_date: dt.date,
    end_date: dt.date,
    input_fingerprint: str,
    rejected_delivery_count: int,
    ignored_noncomplete_delivery_count: int,
    superseded_revision_count: int,
    schema_versions: list[str],
    normalization_versions: list[str],
    identity_versions: list[str],
    minimum_identity_coverage: float,
    generated_at: dt.datetime | None = None,
) -> OptionSentimentFeasibilityReport:
    expected_sessions = expected_us_sessions(start_date, end_date)
    expected_set = set(expected_sessions)
    observed_set: set[dt.date] = set()
    daily_row_counts: dict[dt.date, int] = {}
    security_counter: Counter[str] = Counter()
    identity_counter: Counter[str] = Counter()
    unmatched_counter: Counter[str] = Counter()
    null_counter: Counter[str] = Counter()
    delivery_mode_counter: Counter[str] = Counter()
    subscription_lags: list[float] = []
    split_underlyings: set[str] = set()
    split_row_count = 0
    critical_nulls = 0
    total_rows = 0
    delivery_count = 0
    metric_accumulators = {
        metric: _MetricAccumulator(metric) for metric in _DISTRIBUTION_FIELDS
    }

    for delivery in deliveries:
        if delivery.delivery_mode not in {"historical", "subscription"}:
            raise ValueError(
                f"unsupported Option Sentiment delivery mode: {delivery.delivery_mode}"
            )
        if delivery.trade_date not in expected_set:
            raise ValueError(
                "evaluation inputs include dates outside the requested trading sessions"
            )
        if delivery.trade_date in observed_set:
            raise ValueError(
                f"evaluation contains duplicate canonical session {delivery.trade_date}"
            )
        observed_set.add(delivery.trade_date)
        delivery_count += 1
        frame = delivery.frame
        daily_row_counts[delivery.trade_date] = frame.height
        total_rows += frame.height
        security_counter.update(_counts(frame, "underlying_security_type"))
        identity_counter.update(_counts(frame, "identity_status"))
        unmatched_counter.update(
            _counts(
                frame.filter(
                    pl.col("identity_status").is_in(["unmatched", "ambiguous"])
                ),
                "underlying_symbol",
            )
        )
        nulls = frame.null_count().row(0, named=True)
        null_counter.update({field: int(value) for field, value in nulls.items()})
        critical_nulls += sum(
            int(nulls.get(field, 0))
            for field in _CRITICAL_FIELDS
        )
        split_rows = frame.filter(
            (pl.col("spot_close") - pl.col("split_adj_close")).abs()
            > pl.max_horizontal(
                pl.lit(0.01),
                pl.col("spot_close").abs() * 0.000001,
            )
        )
        split_row_count += split_rows.height
        split_underlyings.update(
            str(symbol)
            for symbol in split_rows.get_column("underlying_symbol").unique().to_list()
        )
        delivery_mode_counter[delivery.delivery_mode] += 1
        if delivery.delivery_mode == "subscription":
            subscription_lags.append(
                (delivery.known_at - delivery.effective_at).total_seconds() / 3600
            )
        _accumulate_metrics(
            frame,
            metric_accumulators,
            sample_seed=int(delivery.trade_date.strftime("%Y%m%d")),
        )

    missing_sessions = sorted(expected_set - observed_set)
    coverage = len(observed_set) / len(expected_sessions) if expected_sessions else 0.0
    daily_rows = pl.DataFrame(
        {
            "trade_date": list(daily_row_counts),
            "row_count": list(daily_row_counts.values()),
        },
        schema={"trade_date": pl.Date, "row_count": pl.UInt32},
    )
    daily_distribution = _distribution(daily_rows, "row_count")
    median_daily_rows = daily_distribution.median or 0
    low_breadth_sessions = (
        sorted(
            trade_date
            for trade_date, row_count in daily_row_counts.items()
            if row_count < median_daily_rows * 0.8
        )
        if median_daily_rows
        else []
    )

    security_type_counts = dict(sorted(security_counter.items()))
    identity_status_counts = dict(sorted(identity_counter.items()))
    stock_rows = sum(
        identity_status_counts.get(key, 0)
        for key in ("matched", "unmatched", "ambiguous")
    )
    matched_rows = identity_status_counts.get("matched", 0)
    identity_coverage = matched_rows / stock_rows if stock_rows else 0.0
    unmatched_stock_symbols = [
        {"symbol": symbol, "sessions": sessions}
        for symbol, sessions in unmatched_counter.most_common(50)
    ]
    null_rates = {
        field: count / total_rows
        for field, count in sorted(null_counter.items())
    } if total_rows else {}
    distributions = {
        metric: accumulator.summary()
        for metric, accumulator in metric_accumulators.items()
    }
    delivery_modes = dict(sorted(delivery_mode_counter.items()))
    lag_frame = pl.DataFrame({"lag": subscription_lags})
    subscription_lag = _distribution(lag_frame, "lag") if subscription_lags else None

    minimum_session_requirement = min(MIN_ONE_YEAR_SESSIONS, len(expected_sessions))
    gates = [
        EvaluationGate(
            name="one_year_session_depth",
            passed=delivery_count >= minimum_session_requirement,
            observed=f"{delivery_count} canonical complete sessions",
            requirement=f"at least {minimum_session_requirement}",
        ),
        EvaluationGate(
            name="calendar_coverage",
            passed=coverage >= MIN_CALENDAR_COVERAGE,
            observed=f"{coverage:.2%}",
            requirement=f"at least {MIN_CALENDAR_COVERAGE:.0%}",
        ),
        EvaluationGate(
            name="stock_identity_coverage",
            passed=identity_coverage >= minimum_identity_coverage,
            observed=f"{identity_coverage:.2%}",
            requirement=f"at least {minimum_identity_coverage:.2%}",
        ),
        EvaluationGate(
            name="critical_field_completeness",
            passed=critical_nulls == 0,
            observed=f"{critical_nulls} critical null values",
            requirement="zero",
        ),
        EvaluationGate(
            name="rejected_deliveries",
            passed=rejected_delivery_count == 0,
            observed=str(rejected_delivery_count),
            requirement="zero rejected complete deliveries",
        ),
        EvaluationGate(
            name="schema_consistency",
            passed=schema_versions == [CBOE_OPTION_SENTIMENT_SCHEMA_VERSION],
            observed=", ".join(schema_versions) or "none",
            requirement=CBOE_OPTION_SENTIMENT_SCHEMA_VERSION,
        ),
        EvaluationGate(
            name="normalization_consistency",
            passed=normalization_versions == [NORMALIZATION_VERSION],
            observed=", ".join(normalization_versions) or "none",
            requirement=NORMALIZATION_VERSION,
        ),
        EvaluationGate(
            name="identity_method_consistency",
            passed=identity_versions == [IDENTITY_VERSION],
            observed=", ".join(identity_versions) or "none",
            requirement=IDENTITY_VERSION,
        ),
        EvaluationGate(
            name="daily_breadth_stability",
            passed=len(low_breadth_sessions) <= max(2, round(delivery_count * 0.01)),
            observed=f"{len(low_breadth_sessions)} sessions below 80% of median breadth",
            requirement="no more than 1% of sessions, with a two-session tolerance",
        ),
    ]
    if delivery_count < minimum_session_requirement:
        decision = "insufficient_data"
    elif all(gate.passed for gate in gates):
        decision = "ready_for_phase_b_review"
    else:
        decision = "quality_review_required"

    findings = [
        (
            f"Calendar coverage is {coverage:.2%}: {delivery_count} of "
            f"{len(expected_sessions)} expected US sessions."
        ),
        (
            f"Stock identity coverage is {identity_coverage:.2%}; ETFs and indices are reported "
            "separately and do not dilute this gate."
        ),
        (
            f"{split_row_count} rows across {len(split_underlyings)} underlyings have a material "
            "difference between spot_close and split_adj_close and require corporate-action review."
        ),
        (
            "Distribution counts, means, nulls, minima, and maxima are exact. Quantiles use a "
            "deterministic bounded cross-sectional reservoir to protect worker memory."
        ),
    ]
    if delivery_modes.get("historical"):
        findings.append(
            "Historical-order known_at timestamps describe Atlas acquisition time, not normal "
            "subscription delivery latency."
        )
    if rejected_delivery_count:
        findings.append(
            f"{rejected_delivery_count} complete deliveries were rejected and must be resolved."
        )
    if unmatched_stock_symbols:
        findings.append(
            f"{len(unmatched_stock_symbols)} unmatched or ambiguous stock symbols are listed for "
            "security-master remediation."
        )

    return OptionSentimentFeasibilityReport(
        generated_at=generated_at or dt.datetime.now(dt.UTC),
        start_date=start_date,
        end_date=end_date,
        input_fingerprint=input_fingerprint,
        decision=decision,
        expected_session_count=len(expected_sessions),
        canonical_session_count=delivery_count,
        calendar_coverage=coverage,
        missing_sessions=missing_sessions,
        rejected_delivery_count=rejected_delivery_count,
        ignored_noncomplete_delivery_count=ignored_noncomplete_delivery_count,
        superseded_revision_count=superseded_revision_count,
        total_row_count=total_rows,
        daily_row_count=daily_distribution,
        security_type_counts=security_type_counts,
        identity_status_counts=identity_status_counts,
        stock_identity_coverage=identity_coverage,
        unmatched_stock_symbols=unmatched_stock_symbols,
        null_rates=null_rates,
        metric_distributions=distributions,
        distribution_sampling_method=(
            f"up to {MAX_DAILY_DISTRIBUTION_SAMPLE_ROWS} deterministic rows per session; "
            f"maximum {MAX_METRIC_RESERVOIR_VALUES} values per metric"
        ),
        delivery_modes=delivery_modes,
        subscription_delivery_lag_hours=subscription_lag,
        split_adjustment_row_count=split_row_count,
        split_adjustment_underlyings=sorted(split_underlyings)[:100],
        low_breadth_sessions=low_breadth_sessions,
        schema_versions=schema_versions,
        normalization_versions=normalization_versions,
        identity_versions=identity_versions,
        gates=gates,
        findings=findings,
    )


def render_feasibility_markdown(report: OptionSentimentFeasibilityReport) -> str:
    gate_rows = "\n".join(
        f"| {gate.name} | {'PASS' if gate.passed else 'FAIL'} | "
        f"{gate.observed} | {gate.requirement} |"
        for gate in report.gates
    )
    findings = "\n".join(f"- {finding}" for finding in report.findings)
    return (
        "# Cboe Option Sentiment one-year feasibility\n\n"
        f"- Decision: **{report.decision}**\n"
        f"- Period: {report.start_date} through {report.end_date}\n"
        f"- Sessions: {report.canonical_session_count}/{report.expected_session_count} "
        f"({report.calendar_coverage:.2%})\n"
        f"- Rows: {report.total_row_count:,}\n"
        f"- Stock identity coverage: {report.stock_identity_coverage:.2%}\n"
        f"- Rejected complete deliveries: {report.rejected_delivery_count}\n"
        f"- Superseded revisions: {report.superseded_revision_count}\n"
        f"- Distribution sampling: {report.distribution_sampling_method}\n"
        f"- Input fingerprint: `{report.input_fingerprint}`\n\n"
        "## Gates\n\n"
        "| Gate | Result | Observed | Requirement |\n"
        "|---|---:|---|---|\n"
        f"{gate_rows}\n\n"
        "## Findings\n\n"
        f"{findings}\n"
    )


async def run_option_sentiment_feasibility(
    session: AsyncSession,
    *,
    start_date: dt.date,
    end_date: dt.date,
    store: ImmutableObjectStore | None = None,
    settings: Settings | None = None,
) -> tuple[ResearchDatasetEvaluation, OptionSentimentFeasibilityReport]:
    configured = settings or get_settings()
    if not configured.us_options_phase_a_enabled:
        raise RuntimeError("US options Phase A ingestion is disabled")
    await _bind_shared_research_scope(session)
    await _entitlement(session, on_date=dt.datetime.now(dt.UTC).date())
    snapshots = list(
        await session.scalars(
            select(ResearchDatasetSnapshot)
            .where(
                ResearchDatasetSnapshot.tenant_id == TENANT_ID,
                ResearchDatasetSnapshot.market == MARKET,
                ResearchDatasetSnapshot.dataset_key == DATASET_KEY,
                ResearchDatasetSnapshot.trade_date >= start_date,
                ResearchDatasetSnapshot.trade_date <= end_date,
            )
            .order_by(
                ResearchDatasetSnapshot.trade_date,
                ResearchDatasetSnapshot.known_at,
            )
        )
    )
    fingerprint = _input_fingerprint(snapshots)
    existing = await session.scalar(
        select(ResearchDatasetEvaluation).where(
            ResearchDatasetEvaluation.tenant_id == TENANT_ID,
            ResearchDatasetEvaluation.market == MARKET,
            ResearchDatasetEvaluation.dataset_key == DATASET_KEY,
            ResearchDatasetEvaluation.start_date == start_date,
            ResearchDatasetEvaluation.end_date == end_date,
            ResearchDatasetEvaluation.methodology_version == METHODOLOGY_VERSION,
            ResearchDatasetEvaluation.input_fingerprint == fingerprint,
        )
    )
    target = store or object_store(configured)
    if existing is not None:
        report_payload = target.get(
            key=existing.report_object_key,
            max_bytes=10 * 1024 * 1024,
        )
        if hashlib.sha256(report_payload).hexdigest() != existing.report_sha256:
            raise RuntimeError("stored feasibility report hash does not match its manifest")
        return existing, OptionSentimentFeasibilityReport.model_validate_json(report_payload)

    canonical, rejected, ignored, superseded = _canonical_snapshots(snapshots)
    def delivery_stream() -> Iterable[EvaluationDelivery]:
        for snapshot in canonical:
            if not snapshot.normalized_object_key or not snapshot.normalized_sha256:
                raise RuntimeError(f"accepted snapshot {snapshot.id} has no normalized artifact")
            payload = target.get(
                key=snapshot.normalized_object_key,
                max_bytes=MAX_NORMALIZED_PARQUET_BYTES,
            )
            if hashlib.sha256(payload).hexdigest() != snapshot.normalized_sha256:
                raise RuntimeError(
                    f"normalized artifact hash mismatch for snapshot {snapshot.id}"
                )
            yield EvaluationDelivery(
                snapshot_id=str(snapshot.id),
                trade_date=snapshot.trade_date,
                effective_at=snapshot.effective_at,
                known_at=snapshot.known_at,
                delivery_mode=str(
                    snapshot.source_metadata.get("delivery_mode", "historical")
                ),
                frame=_prepare_frame(payload, trade_date=snapshot.trade_date),
            )

    report = evaluate_option_sentiment(
        delivery_stream(),
        start_date=start_date,
        end_date=end_date,
        input_fingerprint=fingerprint,
        rejected_delivery_count=rejected,
        ignored_noncomplete_delivery_count=ignored,
        superseded_revision_count=superseded,
        schema_versions=sorted({snapshot.schema_version for snapshot in canonical}),
        normalization_versions=sorted(
            {snapshot.normalization_version for snapshot in canonical}
        ),
        identity_versions=sorted({snapshot.identity_version for snapshot in canonical}),
        minimum_identity_coverage=configured.us_options_min_identity_coverage,
    )
    report_payload = report.model_dump_json(indent=2).encode()
    report_key = (
        f"us/options/{DATASET_KEY}/evaluations/method={METHODOLOGY_VERSION}/"
        f"start={start_date.isoformat()}/end={end_date.isoformat()}/"
        f"{fingerprint}.json"
    )
    stored = target.put(
        key=report_key,
        payload=report_payload,
        content_type="application/json",
        metadata={
            "dataset": DATASET_KEY,
            "methodology": METHODOLOGY_VERSION,
            "input-fingerprint": fingerprint,
        },
    )
    evaluation = ResearchDatasetEvaluation(
        tenant_id=TENANT_ID,
        market=MARKET,
        dataset_key=DATASET_KEY,
        start_date=start_date,
        end_date=end_date,
        methodology_version=METHODOLOGY_VERSION,
        input_fingerprint=fingerprint,
        generated_at=report.generated_at,
        decision=report.decision,
        canonical_snapshot_count=report.canonical_session_count,
        report_object_key=stored.key,
        report_sha256=stored.sha256,
        summary={
            "expected_session_count": report.expected_session_count,
            "calendar_coverage": report.calendar_coverage,
            "total_row_count": report.total_row_count,
            "stock_identity_coverage": report.stock_identity_coverage,
            "rejected_delivery_count": report.rejected_delivery_count,
            "failed_gates": [gate.name for gate in report.gates if not gate.passed],
        },
    )
    session.add(evaluation)
    await session.flush()
    return evaluation, report
