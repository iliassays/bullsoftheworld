"""Scheduled catalyst collection only targets tenants whose Atlas product is open."""

from __future__ import annotations

from api.institutional_research.worker import WorkerSettings, research_collection_targets
from bulls.core.tenancy import Tenant


def _tenant(name: str, market: str, research_access: str) -> Tenant:
    return Tenant(
        name=name,
        display_name=name,
        market=market,
        locale="en",
        site_url=f"https://{name}.com",
        support_email=f"hello@{name}.com",
        email_from=f"no-reply@{name}.com",
        logo_url="/logo.png",
        tagline_en="",
        tagline_bn="",
        research_access=research_access,  # type: ignore[arg-type]
    )


def test_closed_tenants_are_never_collected() -> None:
    targets = research_collection_targets(
        [
            _tenant("bullsofdhaka", "DSE", "authenticated"),
            _tenant("bullsofwallst", "US", "authenticated"),
            _tenant("bullsofusa", "US", "closed"),
        ]
    )

    assert targets == [("bullsofdhaka", "DSE"), ("bullsofwallst", "US")]


def test_worker_schedules_post_close_catalyst_crons() -> None:
    names = {job.name for job in WorkerSettings.cron_jobs}

    assert names == {"catalysts_post_dse", "catalysts_post_us"}
