"""Versioned, hash-stable cohort manifests and onboarding policy."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SYMBOL_RE = re.compile(r"^[A-Z0-9.-]{1,16}$")


class OnboardingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed_instrument_types: tuple[str, ...] = ("common_stock", "adr", "etf")
    min_bars: int = Field(default=1250, ge=252, le=6000)
    min_history_days: int = Field(default=1460, ge=365, le=7305)
    max_staleness_days: int = Field(default=10, ge=1, le=30)
    min_adjusted_close_ratio: float = Field(default=0.98, ge=0, le=1)
    min_nonzero_volume_ratio: float = Field(default=0.95, ge=0, le=1)
    require_cik_for: tuple[str, ...] = ("common_stock", "adr")
    sec_filings_required_for: tuple[str, ...] = ("common_stock", "adr")
    sec_facts_required_for: tuple[str, ...] = ("common_stock",)
    min_sec_filings: int = Field(default=1, ge=0, le=100)
    min_sec_facts: int = Field(default=1, ge=0, le=1000)
    require_analytics: bool = True
    require_13f: bool = False
    min_market_cap_mn: float | None = Field(default=None, gt=0)
    max_market_cap_mn: float | None = Field(default=None, gt=0)
    min_adtv_mn: float | None = Field(default=None, gt=0)
    min_price: float | None = Field(default=None, gt=0)
    requires_risk_review: bool = False

    @model_validator(mode="after")
    def validate_market_cap_range(self) -> OnboardingPolicy:
        if (
            self.min_market_cap_mn is not None
            and self.max_market_cap_mn is not None
            and self.min_market_cap_mn >= self.max_market_cap_mn
        ):
            raise ValueError("min_market_cap_mn must be below max_market_cap_mn")
        return self


class CohortManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1, le=1)
    name: str = Field(min_length=1, max_length=96)
    version: str = Field(default="1", min_length=1, max_length=32)
    market: str
    backfill_years: float = Field(default=10, ge=1, le=20)
    description: str = Field(default="", max_length=500)
    risk_review_id: str | None = Field(default=None, min_length=3, max_length=128)
    symbols: tuple[str, ...]
    policy: OnboardingPolicy = Field(default_factory=OnboardingPolicy)
    manifest_sha256: str = Field(min_length=64, max_length=64)

    @field_validator("market")
    @classmethod
    def normalize_market(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("symbols", mode="before")
    @classmethod
    def normalize_symbols(cls, value):
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("cohort symbols must be a non-empty list")
        return tuple(str(code).strip().upper() for code in value)

    @model_validator(mode="after")
    def validate_symbols(self) -> CohortManifest:
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("cohort symbols must be unique")
        invalid = [code for code in self.symbols if not _SYMBOL_RE.fullmatch(code)]
        if invalid:
            raise ValueError(f"invalid cohort symbols: {', '.join(invalid)}")
        return self


def load_cohort(path: str | Path, expected_market: str) -> CohortManifest:
    path = Path(path)
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("cohort manifest must be a JSON object")
    market = str(payload.get("market", "")).upper()
    if market != expected_market.upper():
        raise ValueError(f"cohort market {market!r} does not match {expected_market!r}")
    normalized = {
        **payload,
        "name": str(payload.get("name") or path.stem),
        "manifest_sha256": hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    return CohortManifest.model_validate(normalized)
