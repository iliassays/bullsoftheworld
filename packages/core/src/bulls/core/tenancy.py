"""Tenancy — a tenant is *config*, not a fork.

A tenant maps a domain (bullsofdhaka.com) to a market, locale, and branding. The core/api code
is tenant-agnostic; it resolves the active tenant from the request host and reads its config.

Tenant configs live in `tenants/<name>/tenant.toml` and are loaded at startup.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel


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
    timezone: str = "Asia/Dhaka"  # IANA tz for the market's clock (sessions, daily rhythm)
    domains: list[str] = []
    theme: Theme = Theme()


class TenantRegistry:
    """Loads and resolves tenants. Built once at startup."""

    def __init__(self, tenants: dict[str, Tenant], *, default: str) -> None:
        self._by_name = tenants
        self._by_domain = {d: t for t in tenants.values() for d in t.domains}
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
        return self._by_name[self._default]

    def get(self, name: str) -> Tenant | None:
        """Look up a tenant by name (for admin tooling that selects a tenant explicitly)."""
        return self._by_name.get(name)

    def all(self) -> list[Tenant]:
        """Every configured tenant (for the admin tenant selector)."""
        return list(self._by_name.values())
