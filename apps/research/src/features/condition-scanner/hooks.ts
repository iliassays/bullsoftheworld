import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { loadProvisionedResearchWorkspaces } from "../research-queue/useResearchQueue";
import {
  conditionScannerGateway,
  type ConditionScanRequest,
} from "./gateway";
import type { ConditionKey } from "./model";

export function useConditionScannerWorkspaces() {
  return useQuery({
    queryKey: ["research", "workspaces"],
    queryFn: loadProvisionedResearchWorkspaces,
  });
}

export function useConditionScan(
  workspaceId: string | undefined,
  request: ConditionScanRequest,
) {
  return useQuery({
    queryKey: [
      "research",
      "condition-scan",
      workspaceId,
      request.conditionKey,
      request.capTier ?? "all",
      Boolean(request.newOnly),
      request.limit ?? 100,
    ],
    queryFn: ({ signal }) => conditionScannerGateway.loadScan(workspaceId!, request, signal),
    enabled: Boolean(workspaceId),
  });
}

export function useConditionSubscription(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      conditionKey,
      ticker,
      enabled,
    }: {
      conditionKey: ConditionKey;
      ticker: string;
      enabled: boolean;
    }) => conditionScannerGateway.setSubscription(
      workspaceId!,
      conditionKey,
      ticker,
      enabled,
    ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["research", "condition-scan", workspaceId] });
    },
  });
}
