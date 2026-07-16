"""Screens caching: stable last-known-good keys and warm-size resolution."""

from __future__ import annotations

import datetime as dt

from api.routers.screener import screens_cache_keys
from api.warm_screens import warm_sizes

_QUOTE_TS = dt.datetime(2026, 7, 16, 8, 45, tzinfo=dt.UTC)
_ANA_TS = dt.datetime(2026, 7, 16, 13, 36, tzinfo=dt.UTC)


def test_fresh_key_rotates_with_data_but_stale_key_stays_stable() -> None:
    fresh_a, stale_a = screens_cache_keys("bullsofdhaka", "DSE", None, _QUOTE_TS, _ANA_TS)
    fresh_b, stale_b = screens_cache_keys(
        "bullsofdhaka", "DSE", None, _QUOTE_TS + dt.timedelta(minutes=15), _ANA_TS
    )

    assert fresh_a != fresh_b  # quote rotation invalidates the fresh copy
    assert stale_a == stale_b  # ...but never the last-known-good fallback
    assert "stale" in stale_a and "stale" not in fresh_a


def test_cache_keys_are_scoped_per_tenant_market_and_size() -> None:
    _, dse = screens_cache_keys("bullsofdhaka", "DSE", None, _QUOTE_TS, _ANA_TS)
    _, us = screens_cache_keys("bullsofwallst", "US", None, _QUOTE_TS, _ANA_TS)
    _, dse_mid = screens_cache_keys("bullsofdhaka", "DSE", "mid", _QUOTE_TS, _ANA_TS)

    assert len({dse, us, dse_mid}) == 3


def test_warm_sizes_defaults_to_all_plus_every_market_tier() -> None:
    sizes = warm_sizes("DSE", None)

    assert sizes[0] is None  # the unfiltered default view
    assert set(sizes[1:]) == {"large", "mid", "small", "micro"}


def test_warm_sizes_honours_explicit_selection() -> None:
    assert warm_sizes("DSE", "all,mid") == [None, "mid"]
