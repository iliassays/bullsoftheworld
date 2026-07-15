import { researchApi, type ResearchWorkspace } from "../../app/api-client";
import { isResearchPreview, researchDeployment } from "../../app/deployment";
import { demoQueueSnapshot } from "./preview-data";
import type { CapTierFilter, ResearchQueueSnapshot } from "./model";

export interface ResearchQueueRequest {
  capTier?: CapTierFilter;
  query?: string;
}

export interface ResearchQueueGateway {
  loadWorkspaces(): Promise<ResearchWorkspace[]>;
  bootstrapWorkspace(): Promise<ResearchWorkspace>;
  loadQueue(
    workspaceId: string,
    request?: ResearchQueueRequest,
    signal?: AbortSignal,
  ): Promise<ResearchQueueSnapshot>;
}

const previewWorkspace: ResearchWorkspace = {
  id: "00000000-0000-0000-0000-000000000001",
  organizationId: "00000000-0000-0000-0000-000000000001",
  organizationName: "Demonstration workspace",
  tenantId: researchDeployment.tenant,
  market: researchDeployment.market,
  name: "Preview research",
  baseCurrency: researchDeployment.currency,
  organizationRole: "owner",
  workspaceRole: "portfolio_manager",
};

class PreviewResearchQueueGateway implements ResearchQueueGateway {
  async loadWorkspaces(): Promise<ResearchWorkspace[]> {
    return [previewWorkspace];
  }

  async bootstrapWorkspace(): Promise<ResearchWorkspace> {
    return previewWorkspace;
  }

  async loadQueue(
    _workspaceId: string,
    request: ResearchQueueRequest = {},
    signal?: AbortSignal,
  ): Promise<ResearchQueueSnapshot> {
    await new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(resolve, 180);
      signal?.addEventListener(
        "abort",
        () => {
          window.clearTimeout(timer);
          reject(new DOMException("Request aborted", "AbortError"));
        },
        { once: true },
      );
    });
    const candidates = demoQueueSnapshot.candidates.filter((candidate) => {
      if (candidate.market !== researchDeployment.market) return false;
      if (request.capTier && request.capTier !== "all" && candidate.capTier !== request.capTier) {
        return false;
      }
      const query = request.query?.trim().toLowerCase();
      return !query || `${candidate.ticker} ${candidate.company} ${candidate.sector}`.toLowerCase().includes(query);
    });
    return {
      ...demoQueueSnapshot,
      tenantId: researchDeployment.tenant,
      market: researchDeployment.market,
      workspaceId: previewWorkspace.id,
      universeCount: demoQueueSnapshot.candidates.filter(
        (candidate) => candidate.market === researchDeployment.market,
      ).length,
      eligibleCount: candidates.length,
      returnedCount: candidates.length,
      candidates,
    };
  }
}

class ApiResearchQueueGateway implements ResearchQueueGateway {
  loadWorkspaces(): Promise<ResearchWorkspace[]> {
    return researchApi.workspaces();
  }

  bootstrapWorkspace(): Promise<ResearchWorkspace> {
    return researchApi.bootstrapWorkspace();
  }

  loadQueue(
    workspaceId: string,
    request: ResearchQueueRequest = {},
    signal?: AbortSignal,
  ): Promise<ResearchQueueSnapshot> {
    return researchApi.queue(workspaceId, request, signal);
  }
}

export const researchQueueGateway: ResearchQueueGateway = isResearchPreview
  ? new PreviewResearchQueueGateway()
  : new ApiResearchQueueGateway();
