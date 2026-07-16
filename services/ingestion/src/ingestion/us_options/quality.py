"""Identity reconciliation and Phase A quality gates for Option Sentiment."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import BaseModel, Field

from bulls.market_data.options.cboe_sentiment import (
    CboeOptionSentimentRecord,
    OptionSentimentCompleteness,
)

NORMALIZATION_VERSION = "atlas-option-sentiment-normalization-v1"
IDENTITY_VERSION = "us-security-master-options-alias-v1"


@dataclass(frozen=True, slots=True)
class SecurityAlias:
    canonical_code: str
    aliases: tuple[str, ...]


class NormalizedOptionSentimentRow(BaseModel):
    canonical_code: str | None
    identity_status: str
    trade_date: str
    underlying_symbol: str
    underlying_security_type: str
    values: dict[str, int | float | str | None]

    def flat(self) -> dict[str, int | float | str | None]:
        return {
            "canonical_code": self.canonical_code,
            "identity_status": self.identity_status,
            **self.values,
        }


class OptionSentimentQualityReport(BaseModel):
    passed: bool
    reasons: list[str]
    row_count: int
    stock_rows: int
    matched_stock_rows: int
    unmatched_stock_rows: int
    ambiguous_stock_rows: int
    stock_identity_coverage: float = Field(ge=0, le=1)
    etf_rows: int
    index_rows: int
    null_counts: dict[str, int]
    identity_version: str = IDENTITY_VERSION
    normalization_version: str = NORMALIZATION_VERSION


def _alias_index(securities: Iterable[SecurityAlias]) -> dict[str, str | None]:
    candidates: dict[str, set[str]] = defaultdict(set)
    for security in securities:
        for alias in security.aliases:
            clean = alias.strip()
            if clean:
                candidates[clean].add(security.canonical_code)
    return {
        alias: next(iter(codes)) if len(codes) == 1 else None
        for alias, codes in candidates.items()
    }


def normalize_option_sentiment(
    records: Iterable[CboeOptionSentimentRecord],
    *,
    securities: Iterable[SecurityAlias],
    completeness: OptionSentimentCompleteness,
    minimum_identity_coverage: float,
) -> tuple[list[NormalizedOptionSentimentRow], OptionSentimentQualityReport, str]:
    aliases = _alias_index(securities)
    rows: list[NormalizedOptionSentimentRow] = []
    null_counts: Counter[str] = Counter()
    stock_rows = matched = unmatched = ambiguous = etf_rows = index_rows = 0

    for record in records:
        values = record.model_dump(mode="json")
        for key, value in values.items():
            if value is None:
                null_counts[key] += 1
        canonical_code = None
        if record.underlying_security_type == "S":
            stock_rows += 1
            if record.underlying_symbol not in aliases:
                identity_status = "unmatched"
                unmatched += 1
            elif aliases[record.underlying_symbol] is None:
                identity_status = "ambiguous"
                ambiguous += 1
            else:
                identity_status = "matched"
                canonical_code = aliases[record.underlying_symbol]
                matched += 1
        elif record.underlying_security_type == "E":
            identity_status = "excluded_etf"
            etf_rows += 1
        else:
            identity_status = "excluded_index"
            index_rows += 1
        rows.append(
            NormalizedOptionSentimentRow(
                canonical_code=canonical_code,
                identity_status=identity_status,
                trade_date=record.trade_date.isoformat(),
                underlying_symbol=record.underlying_symbol,
                underlying_security_type=record.underlying_security_type,
                values=values,
            )
        )

    coverage = matched / stock_rows if stock_rows else 0.0
    reasons: list[str] = []
    if not rows:
        reasons.append("dataset contains no rows")
    if stock_rows == 0:
        reasons.append("dataset contains no stock underlyings")
    if coverage < minimum_identity_coverage:
        reasons.append(
            f"stock identity coverage {coverage:.2%} is below {minimum_identity_coverage:.2%}"
        )
    if completeness == "preliminary":
        reasons.append("preliminary files cannot become the canonical research dataset")
    report = OptionSentimentQualityReport(
        passed=not reasons,
        reasons=reasons,
        row_count=len(rows),
        stock_rows=stock_rows,
        matched_stock_rows=matched,
        unmatched_stock_rows=unmatched,
        ambiguous_stock_rows=ambiguous,
        stock_identity_coverage=coverage,
        etf_rows=etf_rows,
        index_rows=index_rows,
        null_counts=dict(sorted(null_counts.items())),
    )
    canonical = json.dumps(
        [row.model_dump(mode="json") for row in sorted(rows, key=lambda item: item.underlying_symbol)],
        sort_keys=True,
        separators=(",", ":"),
    )
    return rows, report, hashlib.sha256(canonical.encode()).hexdigest()
