import { useQuery } from "@tanstack/react-query";

import { researchApi } from "../../app/api-client";
import { isResearchPreview } from "../../app/deployment";
import { previewDecisionBoard, previewDecisionPath } from "./preview-data";

export function useDecisionBoard(
  workspaceId: string | undefined,
  asOf: string | undefined,
) {
  return useQuery({
    queryKey: ["research", "decision-board", workspaceId, asOf ?? "latest"],
    queryFn: () => {
      if (!isResearchPreview) return researchApi.decisionBoard(workspaceId!, asOf);
      return Promise.resolve({
        ...previewDecisionBoard,
        selectedDate: asOf ?? previewDecisionBoard.selectedDate,
      });
    },
    enabled: Boolean(workspaceId),
    refetchInterval: asOf ? false : 30_000,
  });
}

export function useDecisionCandidatePath(
  workspaceId: string | undefined,
  portfolioId: string | undefined,
  code: string | undefined,
  asOf: string | undefined,
) {
  return useQuery({
    queryKey: [
      "research",
      "decision-path",
      workspaceId,
      portfolioId,
      code,
      asOf ?? "latest",
    ],
    queryFn: () => isResearchPreview
      ? Promise.resolve(previewDecisionPath(portfolioId!, code!))
      : researchApi.decisionCandidatePath(workspaceId!, portfolioId!, code!, asOf),
    enabled: Boolean(workspaceId && portfolioId && code),
  });
}
