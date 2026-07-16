"""Warm the /screens cache off-request so users only ever hit Redis.

Runs from systemd timers (infra/systemd/*-screens-warm.*) with a raised
DATABASE_STATEMENT_TIMEOUT_MS, because the whole point is to do the heavy multi-screen compute
where a slow shared host cannot turn it into a user-facing 500. Each successful build also
refreshes the last-known-good copy that the API serves when an in-request rebuild times out.

    uv run python -m api.warm_screens bullsofdhaka
    uv run python -m api.warm_screens bullsofwallst --sizes all,large,mid
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import redis.asyncio as aioredis

from api.routers.scanner import (
    build_and_cache_radar,
    radar_data_timestamps,
    scanner_pack_for,
)
from api.routers.screener import (
    build_and_cache_screens,
    screens_data_timestamps,
)
from bulls.core.config import get_settings
from bulls.core.db import get_sessionmaker
from bulls.core.markets import get_market_profile
from bulls.core.tenancy import TenantRegistry

log = logging.getLogger("warm_screens")

_TENANTS_DIR = Path(__file__).resolve().parents[4] / "tenants"


def warm_sizes(market: str, requested: str | None) -> list[str | None]:
    """Resolve the size list; 'all' means the unfiltered default view."""
    if requested:
        return [None if item == "all" else item for item in requested.split(",") if item]
    return [None, *(tier for tier, _ in get_market_profile(market).cap_tiers)]


async def warm_tenant(tenant_name: str, requested_sizes: str | None) -> int:
    registry = TenantRegistry.from_dir(_TENANTS_DIR, default=get_settings().default_tenant)
    tenant = registry.get(tenant_name)
    if tenant is None:
        log.error("unknown tenant %s", tenant_name)
        return 2
    sm = get_sessionmaker()
    redis = aioredis.from_url(get_settings().redis_url)
    failures = 0
    radar_tabs = [tab.key for tab in scanner_pack_for(tenant.market).tabs]
    try:
        for size in warm_sizes(tenant.market, requested_sizes):
            # One session per unit of work: a statement timeout poisons the transaction it
            # happens in, and a fresh session keeps one slow group from failing the rest.
            async with sm() as session:
                try:
                    quote_ts, ana_ts = await screens_data_timestamps(session, tenant.market)
                    resp = await build_and_cache_screens(
                        tenant, session, redis, size=size, quote_ts=quote_ts, ana_ts=ana_ts
                    )
                except Exception:
                    failures += 1
                    log.exception("warm failed for %s size=%s", tenant_name, size or "all")
                else:
                    log.info(
                        "warmed %s/%s size=%s screens=%d",
                        tenant_name,
                        tenant.market,
                        size or "all",
                        len(resp.screens),
                    )
            # The Ideas tab (scanner radar) serves the same shared read-model audience; warm its
            # default (non-watchlist, default-limit) view for every tab at this size.
            for tab in radar_tabs:
                async with sm() as session:
                    try:
                        quote_ts, ana_ts = await radar_data_timestamps(session, tenant.market)
                        await build_and_cache_radar(
                            tenant,
                            session,
                            redis,
                            tab=tab,
                            size=size,
                            limit=10,
                            quote_ts=quote_ts,
                            ana_ts=ana_ts,
                        )
                    except Exception:
                        failures += 1
                        log.exception(
                            "radar warm failed for %s tab=%s size=%s",
                            tenant_name,
                            tab,
                            size or "all",
                        )
                    else:
                        log.info(
                            "warmed radar %s/%s tab=%s size=%s",
                            tenant_name,
                            tenant.market,
                            tab,
                            size or "all",
                        )
    finally:
        await redis.aclose()
    return 1 if failures else 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Warm the /screens cache for one tenant")
    parser.add_argument("tenant", help="tenant name, e.g. bullsofdhaka")
    parser.add_argument(
        "--sizes",
        default=None,
        help="comma-separated cap tiers; 'all' is the unfiltered view (default: all + every tier)",
    )
    args = parser.parse_args(sys.argv[1:])
    raise SystemExit(asyncio.run(warm_tenant(args.tenant, args.sizes)))


if __name__ == "__main__":
    main()
