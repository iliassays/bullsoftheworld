import { afterEach, describe, expect, it, vi } from "vitest";

import { researchApi } from "./api-client";
import { researchDeployment } from "./deployment";

const own = researchDeployment.market === "DSE"
  ? {
      market: "DSE" as const,
      tenantId: "bullsofdhaka" as const,
      ticker: "BSC",
      workspaceId: "workspace-dse",
    }
  : {
      market: "US" as const,
      tenantId: "bullsofwallst" as const,
      ticker: "NXTC",
      workspaceId: "workspace-us",
    };

const foreign = researchDeployment.market === "DSE"
  ? {
      market: "US" as const,
      tenantId: "bullsofwallst" as const,
      ticker: "AAPL",
      workspaceId: "workspace-us",
    }
  : {
      market: "DSE" as const,
      tenantId: "bullsofdhaka" as const,
      ticker: "BSC",
      workspaceId: "workspace-dse",
    };

const strategyKey = own.market === "DSE" ? "dse_reversal_v1" : "us_breakout_v1";

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
            id: foreign.workspaceId,
            organizationId: `organization-${foreign.market.toLowerCase()}`,
            organizationName: `${foreign.market} Research`,
            tenantId: foreign.tenantId,
            market: foreign.market,
            name: "Core Research",
            baseCurrency: foreign.market === "DSE" ? "BDT" : "USD",
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
        tenantId: own.tenantId,
        market: own.market,
        workspaceId: own.workspaceId,
        generatedAt: "2026-07-15T00:00:00Z",
        knowledgeCutoffAt: "2026-07-15T00:00:00Z",
        candidates: [{ id: `${foreign.market}:${foreign.ticker}`, market: foreign.market }],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(researchApi.queue(own.workspaceId)).rejects.toMatchObject({
      status: 502,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Tenant-Host": researchDeployment.tenantHost,
        }),
      }),
    );
  });

  it("serializes queue filters for server-side universe selection", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        tenantId: own.tenantId,
        market: own.market,
        workspaceId: own.workspaceId,
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

    await researchApi.queue(own.workspaceId, {
      capTier: "small",
      query: "  BSC & bank  ",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining(
        `/institutional-research/workspaces/${own.workspaceId}/queue?cap_tier=small&query=BSC+%26+bank`,
      ),
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("rejects a dossier returned for another ticker or market", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          tenantId: own.tenantId,
          market: own.market,
          workspaceId: own.workspaceId,
          candidate: {
            market: foreign.market,
            ticker: foreign.ticker,
          },
        }),
      ),
    );

    await expect(researchApi.dossier(own.workspaceId, ` ${own.ticker.toLowerCase()} `)).rejects.toMatchObject({
      status: 502,
    });
  });

  it("normalizes the requested ticker before loading a tenant-safe dossier", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        tenantId: own.tenantId,
        market: own.market,
        workspaceId: own.workspaceId,
        candidate: {
          market: own.market,
          ticker: own.ticker,
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await researchApi.dossier(own.workspaceId, ` ${own.ticker.toLowerCase()} `);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining(
        `/institutional-research/workspaces/${own.workspaceId}/companies/${own.ticker}`,
      ),
      expect.objectContaining({
        credentials: "include",
        headers: expect.objectContaining({
          "X-Tenant-Host": researchDeployment.tenantHost,
        }),
      }),
    );
  });

  it("rejects autonomous runs crossing the workspace boundary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          id: `run-${foreign.market.toLowerCase()}`,
          workspaceId: foreign.workspaceId,
          tenantId: foreign.tenantId,
          market: foreign.market,
        }),
      ),
    );

    await expect(researchApi.startCompanyResearch(own.workspaceId, own.ticker)).rejects.toMatchObject({
      status: 502,
    });
  });

  it("rejects a shadow portfolio crossing the market boundary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse([
          {
            id: `portfolio-${foreign.market.toLowerCase()}`,
            workspaceId: own.workspaceId,
            tenantId: own.tenantId,
            market: foreign.market,
          },
        ]),
      ),
    );

    await expect(researchApi.reconcileShadowPortfolios(own.workspaceId)).rejects.toMatchObject({
      status: 502,
    });
  });

  it("rejects calibration observations without the requested tenant envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          workspaceId: own.workspaceId,
          tenantId: foreign.tenantId,
          market: foreign.market,
          pending: 0,
          matured: 0,
          buckets: [],
          observations: [],
        }),
      ),
    );

    await expect(researchApi.calibration(own.workspaceId)).rejects.toMatchObject({ status: 502 });
  });

  it("rejects a statistical model audit from another market", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          tenantId: foreign.tenantId,
          market: foreign.market,
          generatedAt: "2026-08-04T10:00:00Z",
          foundation: null,
          experiment: null,
          methodology: "test",
        }),
      ),
    );

    await expect(researchApi.modelExperiment()).rejects.toMatchObject({ status: 502 });
  });

  it("rejects an automation policy crossing the market boundary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          id: `policy-${foreign.market.toLowerCase()}`,
          workspaceId: own.workspaceId,
          tenantId: foreign.tenantId,
          market: foreign.market,
        }),
      ),
    );

    await expect(researchApi.automationPolicy(own.workspaceId)).rejects.toMatchObject({
      status: 502,
    });
  });

  it("rejects a nested strategy trial crossing the investment boundary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          workspaceId: own.workspaceId,
          tenantId: own.tenantId,
          market: own.market,
          mandate: {
            workspaceId: own.workspaceId,
            tenantId: own.tenantId,
            market: own.market,
          },
          trials: [
            {
              workspaceId: foreign.workspaceId,
              tenantId: foreign.tenantId,
              market: foreign.market,
            },
          ],
          portfolios: [],
        }),
      ),
    );

    await expect(researchApi.investmentOperatingView(own.workspaceId)).rejects.toMatchObject({
      status: 502,
    });
  });

  it("rejects a portfolio mandate crossing the investment boundary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          workspaceId: own.workspaceId,
          tenantId: own.tenantId,
          market: own.market,
          mandate: {
            workspaceId: own.workspaceId,
            tenantId: own.tenantId,
            market: own.market,
          },
          trials: [],
          portfolios: [
            {
              mandate: {
                workspaceId: foreign.workspaceId,
                tenantId: foreign.tenantId,
                market: foreign.market,
              },
            },
          ],
        }),
      ),
    );

    await expect(researchApi.investmentOperatingView(own.workspaceId)).rejects.toMatchObject({
      status: 502,
    });
  });

  it("rejects malformed nested portfolio analytics before they reach rendering", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          workspaceId: own.workspaceId,
          tenantId: own.tenantId,
          market: own.market,
          mandate: {
            workspaceId: own.workspaceId,
            tenantId: own.tenantId,
            market: own.market,
          },
          trials: [],
          portfolios: [
            {
              mandate: {
                workspaceId: own.workspaceId,
                tenantId: own.tenantId,
                market: own.market,
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

    await expect(researchApi.investmentOperatingView(own.workspaceId)).rejects.toMatchObject({
      status: 502,
    });
  });

  it("sends a complete bounded automation policy to the workspace endpoint", async () => {
    const body = {
      id: `policy-${own.market.toLowerCase()}`,
      workspaceId: own.workspaceId,
      tenantId: own.tenantId,
      market: own.market,
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(body));
    vi.stubGlobal("fetch", fetchMock);

    await researchApi.configureAutomation(own.workspaceId, {
      enabled: true,
      queue_limit: 20,
      research_limit: 5,
      cap_tier: "small",
      strategy_key: strategyKey,
      universe_limit: 25,
      initial_capital: 10_000_000,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining(`/workspaces/${own.workspaceId}/automation`),
      expect.objectContaining({
        method: "PUT",
        body: expect.stringContaining(`"strategy_key":"${strategyKey}"`),
      }),
    );
  });
});
