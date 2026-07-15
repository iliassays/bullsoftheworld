import { afterEach, describe, expect, it, vi } from "vitest";

import type { ResearchWorkspace } from "../../app/api-client";
import { researchDeployment } from "../../app/deployment";
import { researchQueueGateway } from "./gateway";
import { loadProvisionedResearchWorkspaces } from "./useResearchQueue";

const workspace: ResearchWorkspace = {
  id: "00000000-0000-0000-0000-000000000101",
  organizationId: "00000000-0000-0000-0000-000000000102",
  organizationName: "Private research",
  tenantId: researchDeployment.tenant,
  market: researchDeployment.market,
  name: "Core equity",
  baseCurrency: researchDeployment.currency,
  organizationRole: "owner",
  workspaceRole: "portfolio_manager",
};

describe("loadProvisionedResearchWorkspaces", () => {
  afterEach(() => vi.restoreAllMocks());

  it("returns an existing tenant workspace without provisioning another", async () => {
    vi.spyOn(researchQueueGateway, "loadWorkspaces").mockResolvedValue([workspace]);
    const bootstrap = vi.spyOn(researchQueueGateway, "bootstrapWorkspace");

    await expect(loadProvisionedResearchWorkspaces()).resolves.toEqual([workspace]);
    expect(bootstrap).not.toHaveBeenCalled();
  });

  it("provisions exactly one workspace when the account has none", async () => {
    vi.spyOn(researchQueueGateway, "loadWorkspaces").mockResolvedValue([]);
    const bootstrap = vi
      .spyOn(researchQueueGateway, "bootstrapWorkspace")
      .mockResolvedValue(workspace);

    await expect(loadProvisionedResearchWorkspaces()).resolves.toEqual([workspace]);
    expect(bootstrap).toHaveBeenCalledOnce();
  });
});
