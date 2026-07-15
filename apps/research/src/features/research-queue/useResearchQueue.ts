import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { researchQueueGateway, type ResearchQueueRequest } from "./gateway";

export function useResearchWorkspaces() {
  return useQuery({
    queryKey: ["research", "workspaces"],
    queryFn: () => researchQueueGateway.loadWorkspaces(),
  });
}

export function useBootstrapResearchWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => researchQueueGateway.bootstrapWorkspace(),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["research", "workspaces"] });
    },
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
