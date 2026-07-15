import { useQuery } from "@tanstack/react-query";

import { researchQueueGateway, type ResearchQueueRequest } from "./gateway";

export async function loadProvisionedResearchWorkspaces() {
  const workspaces = await researchQueueGateway.loadWorkspaces();
  if (workspaces.length > 0) return workspaces;

  // Open-access tenants provision a private workspace at first Atlas use. The POST is idempotent
  // and serialized server-side, so retries and concurrent tabs remain safe.
  return [await researchQueueGateway.bootstrapWorkspace()];
}

export function useResearchWorkspaces() {
  return useQuery({
    queryKey: ["research", "workspaces"],
    queryFn: loadProvisionedResearchWorkspaces,
  });
}

export function useResearchQueue(
  workspaceId: string | undefined,
  request: ResearchQueueRequest = {},
) {
  return useQuery({
    queryKey: ["research", "queue", workspaceId, request.capTier ?? "all", request.query ?? ""],
    queryFn: ({ signal }) => researchQueueGateway.loadQueue(workspaceId!, request, signal),
    enabled: Boolean(workspaceId),
    placeholderData: (previous) => previous,
  });
}
