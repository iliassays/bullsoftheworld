"""Tenancy — a tenant is *config*, not a fork.

A tenant maps a domain (bullsofdhaka.com) to a market, locale, and branding. The core/api code
is tenant-agnostic; it resolves the active tenant from the request host and reads its config.

Tenant configs live in `tenants/<name>/tenant.toml` and are loaded at startup.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

PORTAL_LOCALES = frozenset({"en", "bn"})


class Theme(BaseModel):
    accent: str = "#F5B82E"  # Bull Gold
    up: str = "#16C784"  # per-tenant: some markets flip green/red
    down: str = "#EA3943"
    dark_first: bool = True


class Tenant(BaseModel):
    name: str  # e.g. "bullsofdhaka"
    display_name: str  # e.g. "Bulls of Dhaka"
    market: str  # MarketId, e.g. "DSE"
    locale: str  # e.g. "bn"
    supported_locales: list[str] = Field(default_factory=lambda: ["en", "bn"])
    timezone: str = "Asia/Dhaka"  # IANA tz for the market's clock (sessions, daily rhythm)
    domains: list[str] = Field(default_factory=list)
    site_url: str
    support_email: str
    email_from: str
    logo_url: str
    tagline_en: str
    tagline_bn: str
    research_beta: bool = False
    social_url: str | None = None
    theme: Theme = Field(default_factory=Theme)

    @model_validator(mode="after")
    def validate_locales(self) -> Tenant:
        normalized = [locale.lower() for locale in self.supported_locales]
        if not normalized:
            raise ValueError("supported_locales must not be empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("supported_locales must not contain duplicates")
        unknown = set(normalized) - PORTAL_LOCALES
        if unknown:
            raise ValueError(f"unsupported portal locales: {sorted(unknown)}")
        self.locale = self.locale.lower()
        self.supported_locales = normalized
        if self.locale not in normalized:
            raise ValueError("tenant locale must be included in supported_locales")
        return self


class TenantRegistry:
    """Loads and resolves tenants. Built once at startup."""

    def __init__(self, tenants: dict[str, Tenant], *, default: str) -> None:
        self._by_name = tenants
        self._by_domain: dict[str, Tenant] = {}
        for tenant in tenants.values():
            for domain in tenant.domains:
                claimed_by = self._by_domain.get(domain)
                if claimed_by is not None and claimed_by.name != tenant.name:
                    # A domain claimed by two tenants makes host-based resolution ambiguous: the
                    # last one loaded would silently win and shadow the other tenant's traffic
                    # (the 2026-07-13 leak: api.bullsofdhaka.com, the shared backend every
                    # tenant's frontend calls, was listed under bullsofdhaka — so its Host header
                    # always resolved to DSE before X-Tenant-Host ever got checked). Fail loudly
                    # at startup instead of shipping that silently.
                    raise ValueError(
                        f"domain {domain!r} is claimed by both tenants "
                        f"{claimed_by.name!r} and {tenant.name!r} — a domain used by more than "
                        "one tenant's frontend (e.g. a shared API host) must not appear in any "
                        "tenant's `domains` list; rely on X-Tenant-Host/origin/referer instead"
                    )
                self._by_domain[domain] = tenant
        self._default = default

    @classmethod
    def from_dir(cls, root: Path, *, default: str) -> TenantRegistry:
        tenants: dict[str, Tenant] = {}
        for cfg in sorted(root.glob("*/tenant.toml")):
            data = tomllib.loads(cfg.read_text())
            tenant = Tenant.model_validate(data)
            tenants[tenant.name] = tenant
        if not tenants:
            raise RuntimeError(f"No tenants found under {root}")
        return cls(tenants, default=default)

    @staticmethod
    def _hostname(value: str | None) -> str | None:
        """Normalize a host or URL-like value into a lowercase hostname."""
        if not value:
            return None
        raw = value.strip().lower()
        if not raw:
            return None
        parsed = urlparse(raw if "://" in raw else f"//{raw}")
        return parsed.hostname

    def resolve(
        self,
        host: str | None,
        *,
        tenant_host: str | None = None,
        origin: str | None = None,
        referer: str | None = None,
    ) -> Tenant:
        """Resolve a tenant from request context; fall back to the default tenant.

        `host` is authoritative when it maps to a tenant. For shared API domains, browser callers can
        identify the frontend tenant through `X-Tenant-Host`; browser-loaded assets fall back to
        Origin/Referer. Only configured tenant domains are accepted.
        """
        return (
            self.resolve_known(
                host,
                tenant_host=tenant_host,
                origin=origin,
                referer=referer,
            )
            or self._by_name[self._default]
        )

    def resolve_known(
        self,
        host: str | None,
        *,
        tenant_host: str | None = None,
        origin: str | None = None,
        referer: str | None = None,
    ) -> Tenant | None:
        """Resolve only configured context, with no default-tenant fallback."""
        candidates = (
            host,
            tenant_host,
            origin,
            referer,
        )
        for candidate in candidates:
            hostname = self._hostname(candidate)
            if hostname in self._by_domain:
                return self._by_domain[hostname]
        return None

    def get(self, name: str) -> Tenant | None:
        """Look up a tenant by name (for admin tooling that selects a tenant explicitly)."""
        return self._by_name.get(name)

    def all(self) -> list[Tenant]:
        """Every configured tenant (for the admin tenant selector)."""
        return list(self._by_name.values())
