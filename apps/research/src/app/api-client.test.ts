import { afterEach, describe, expect, it, vi } from "vitest";

import { researchApi } from "./api-client";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("research API tenant boundary", () => {
  it("rejects a workspace returned for another market tenant", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse([
          {
            id: "workspace-us",
            organizationId: "organization-us",
            organizationName: "US Research",
            tenantId: "bullsofwallst",
            market: "US",
            name: "Core Research",
            baseCurrency: "USD",
            organizationRole: "owner",
            workspaceRole: "portfolio_manager",
          },
        ]),
      ),
    );

    await expect(researchApi.workspaces()).rejects.toMatchObject({
      status: 502,
    });
  });

  it("rejects a queue containing a candidate from another market", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        tenantId: "bullsofdhaka",
        market: "DSE",
        workspaceId: "workspace-dse",
        generatedAt: "2026-07-15T00:00:00Z",
        knowledgeCutoffAt: "2026-07-15T00:00:00Z",
        candidates: [{ id: "US:AAPL", market: "US" }],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(researchApi.queue("workspace-dse")).rejects.toMatchObject({
      status: 502,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Tenant-Host": "research.bullsofdhaka.com",
        }),
      }),
    );
  });

  it("serializes queue filters for server-side universe selection", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        tenantId: "bullsofdhaka",
        market: "DSE",
        workspaceId: "workspace-dse",
        generatedAt: "2026-07-15T00:00:00Z",
        knowledgeCutoffAt: "2026-07-15T00:00:00Z",
        universeCount: 396,
        eligibleCount: 1,
        returnedCount: 0,
        isTruncated: false,
        candidates: [],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await researchApi.queue("workspace-dse", {
      capTier: "small",
      query: "  BSC & bank  ",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining(
        "/institutional-research/workspaces/workspace-dse/queue?cap_tier=small&query=BSC+%26+bank",
      ),
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("rejects a dossier returned for another ticker or market", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          tenantId: "bullsofdhaka",
          market: "DSE",
          workspaceId: "workspace-dse",
          candidate: {
            market: "US",
            ticker: "AAPL",
          },
        }),
      ),
    );

    await expect(researchApi.dossier("workspace-dse", " bsc ")).rejects.toMatchObject({
      status: 502,
    });
  });

  it("normalizes the requested ticker before loading a tenant-safe dossier", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        tenantId: "bullsofdhaka",
        market: "DSE",
        workspaceId: "workspace-dse",
        candidate: {
          market: "DSE",
          ticker: "BSC",
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await researchApi.dossier("workspace-dse", " bsc ");

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining(
        "/institutional-research/workspaces/workspace-dse/companies/BSC",
      ),
      expect.objectContaining({
        credentials: "include",
        headers: expect.objectContaining({
          "X-Tenant-Host": "research.bullsofdhaka.com",
        }),
      }),
    );
  });

  it("rejects autonomous runs crossing the workspace boundary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          id: "run-us",
          workspaceId: "workspace-us",
          tenantId: "bullsofwallst",
          market: "US",
        }),
      ),
    );

    await expect(researchApi.startCompanyResearch("workspace-dse", "BSC")).rejects.toMatchObject({
      status: 502,
    });
  });

  it("rejects a shadow portfolio crossing the market boundary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse([
          {
            id: "portfolio-us",
            workspaceId: "workspace-dse",
            tenantId: "bullsofdhaka",
            market: "US",
          },
        ]),
      ),
    );

    await expect(researchApi.reconcileShadowPortfolios("workspace-dse")).rejects.toMatchObject({
      status: 502,
    });
  });

  it("rejects calibration observations without the requested tenant envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          workspaceId: "workspace-dse",
          tenantId: "bullsofwallst",
          market: "US",
          pending: 0,
          matured: 0,
          buckets: [],
          observations: [],
        }),
      ),
    );

    await expect(researchApi.calibration("workspace-dse")).rejects.toMatchObject({ status: 502 });
  });

  it("rejects an automation policy crossing the market boundary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          id: "policy-us",
          workspaceId: "workspace-dse",
          tenantId: "bullsofwallst",
          market: "US",
        }),
      ),
    );

    await expect(researchApi.automationPolicy("workspace-dse")).rejects.toMatchObject({
      status: 502,
    });
  });

  it("rejects a nested strategy trial crossing the investment boundary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          workspaceId: "workspace-dse",
          tenantId: "bullsofdhaka",
          market: "DSE",
          mandate: {
            workspaceId: "workspace-dse",
            tenantId: "bullsofdhaka",
            market: "DSE",
          },
          trials: [
            {
              workspaceId: "workspace-us",
              tenantId: "bullsofwallst",
              market: "US",
            },
          ],
          portfolios: [],
        }),
      ),
    );

    await expect(researchApi.investmentOperatingView("workspace-dse")).rejects.toMatchObject({
      status: 502,
    });
  });

  it("rejects a portfolio mandate crossing the investment boundary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          workspaceId: "workspace-dse",
          tenantId: "bullsofdhaka",
          market: "DSE",
          mandate: {
            workspaceId: "workspace-dse",
            tenantId: "bullsofdhaka",
            market: "DSE",
          },
          trials: [],
          portfolios: [
            {
              mandate: {
                workspaceId: "workspace-us",
                tenantId: "bullsofwallst",
                market: "US",
              },
            },
          ],
        }),
      ),
    );

    await expect(researchApi.investmentOperatingView("workspace-dse")).rejects.toMatchObject({
      status: 502,
    });
  });

  it("rejects malformed nested portfolio analytics before they reach rendering", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          workspaceId: "workspace-dse",
          tenantId: "bullsofdhaka",
          market: "DSE",
          mandate: {
            workspaceId: "workspace-dse",
            tenantId: "bullsofdhaka",
            market: "DSE",
          },
          trials: [],
          portfolios: [
            {
              mandate: {
                workspaceId: "workspace-dse",
                tenantId: "bullsofdhaka",
                market: "DSE",
              },
              risk: {
                largestPositionPct: 10,
                largestSectorPct: 20,
                effectivePositions: 3,
                stressScenarios: [{ estimated_loss_pct: 2.5 }],
              },
              attribution: { components: [] },
            },
          ],
        }),
      ),
    );

    await expect(researchApi.investmentOperatingView("workspace-dse")).rejects.toMatchObject({
      status: 502,
    });
  });

  it("sends a complete bounded automation policy to the workspace endpoint", async () => {
    const body = {
      id: "policy-dse",
      workspaceId: "workspace-dse",
      tenantId: "bullsofdhaka",
      market: "DSE",
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(body));
    vi.stubGlobal("fetch", fetchMock);

    await researchApi.configureAutomation("workspace-dse", {
      enabled: true,
      queue_limit: 20,
      research_limit: 5,
      cap_tier: "small",
      strategy_key: "dse_reversal_v1",
      universe_limit: 25,
      initial_capital: 300_000,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/workspaces/workspace-dse/automation"),
      expect.objectContaining({
        method: "PUT",
        body: expect.stringContaining('"strategy_key":"dse_reversal_v1"'),
      }),
    );
  });
});
