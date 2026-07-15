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
});
