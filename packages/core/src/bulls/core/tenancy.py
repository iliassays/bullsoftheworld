"""Tenancy — a tenant is *config*, not a fork.

A tenant maps a domain (bullsofdhaka.com) to a market, locale, and branding. The core/api code
is tenant-agnostic; it resolves the active tenant from the request host and reads its config.

Tenant configs live in `tenants/<name>/tenant.toml` and are loaded at startup.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal
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
    research_site_url: str = ""
    research_alias_urls: list[str] = Field(default_factory=list)
    research_api_url: str = ""
    # Product access policy, independent of PostgreSQL's ``bulls_app`` runtime identity.
    # ``authenticated`` is the temporary open-beta policy; ``closed`` fails every Atlas route.
    research_access: Literal["closed", "authenticated"] = "closed"
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
        configured_research_site = bool(self.research_site_url)
        configured_research_api = bool(self.research_api_url)
        self.research_site_url = self.research_site_url or self.site_url
        self.research_api_url = self.research_api_url or self.site_url
        allowed_hosts = {self._hostname(domain) for domain in self.domains}
        research_host = self._hostname(self.research_site_url)
        if configured_research_site and research_host not in allowed_hosts:
            raise ValueError("research_site_url host must be listed in tenant domains")
        research_api_host = self._hostname(self.research_api_url)
        if configured_research_api and research_api_host not in allowed_hosts:
            raise ValueError("research_api_url host must be listed in tenant domains")
        alias_hosts = [self._hostname(url) for url in self.research_alias_urls]
        if any(host is None or host not in allowed_hosts for host in alias_hosts):
            raise ValueError("research alias hosts must be listed in tenant domains")
        if len(alias_hosts) != len(set(alias_hosts)):
            raise ValueError("research aliases must not contain duplicate hosts")
        if research_host in alias_hosts:
            raise ValueError("research aliases must not duplicate research_site_url")
        return self

    @staticmethod
    def _hostname(value: str) -> str | None:
        parsed = urlparse(value if "://" in value else f"//{value}")
        return parsed.hostname


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
                    # A shared hostname cannot identify a tenant. Fail at startup instead of
                    # letting load order decide which tenant receives the request.
                    raise ValueError(
                        f"domain {domain!r} is claimed by both tenants "
                        f"{claimed_by.name!r} and {tenant.name!r} — a domain used by more than "
                        "one tenant's frontend (for example, a shared API host) must not appear in any "
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
