import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { researchApi } from "../../app/api-client";

export function useResearchRuns(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["research", "runs", workspaceId],
    queryFn: () => researchApi.runs(workspaceId!),
    enabled: Boolean(workspaceId),
    refetchInterval: 15_000,
  });
}

export function useResearchRun(workspaceId: string | undefined, runId: string | undefined) {
  return useQuery({
    queryKey: ["research", "run", workspaceId, runId],
    queryFn: () => researchApi.run(workspaceId!, runId!),
    enabled: Boolean(workspaceId && runId),
  });
}

export function useStartCompanyResearch(workspaceId: string | undefined) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (ticker: string) => researchApi.startCompanyResearch(workspaceId!, ticker),
    onSuccess: (run) => {
      client.setQueryData(["research", "run", workspaceId, run.id], run);
      void client.invalidateQueries({ queryKey: ["research", "runs", workspaceId] });
      void client.invalidateQueries({ queryKey: ["research", "calibration", workspaceId] });
    },
  });
}

export function useRunBacktest(workspaceId: string | undefined) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Parameters<typeof researchApi.backtest>[1]) =>
      researchApi.backtest(workspaceId!, payload),
    onSuccess: (run) => {
      client.setQueryData(["research", "run", workspaceId, run.id], run);
      void client.invalidateQueries({ queryKey: ["research", "runs", workspaceId] });
    },
  });
}

export function useShadowPortfolios(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["research", "portfolios", workspaceId],
    queryFn: () => researchApi.shadowPortfolios(workspaceId!),
    enabled: Boolean(workspaceId),
    refetchInterval: 30_000,
  });
}

export function useCreateShadowPortfolio(workspaceId: string | undefined) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ sourceRunId, name }: { sourceRunId: string; name: string }) =>
      researchApi.createShadowPortfolio(workspaceId!, sourceRunId, name),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["research", "portfolios", workspaceId] }),
  });
}

export function useCalibration(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["research", "calibration", workspaceId],
    queryFn: () => researchApi.calibration(workspaceId!),
    enabled: Boolean(workspaceId),
    staleTime: 0,
  });
}

export function useAutomationPolicy(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["research", "automation", workspaceId],
    queryFn: () => researchApi.automationPolicy(workspaceId!),
    enabled: Boolean(workspaceId),
    refetchInterval: 15_000,
  });
}

export function useConfigureAutomation(workspaceId: string | undefined) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Parameters<typeof researchApi.configureAutomation>[1]) =>
      researchApi.configureAutomation(workspaceId!, payload),
    onSuccess: (policy) => {
      client.setQueryData(["research", "automation", workspaceId], policy);
      void client.invalidateQueries({ queryKey: ["research", "runs", workspaceId] });
    },
  });
}

export function useRunLifecycle(workspaceId: string | undefined) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => researchApi.runLifecycle(workspaceId!),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["research", "automation", workspaceId] });
      void client.invalidateQueries({ queryKey: ["research", "runs", workspaceId] });
    },
  });
}
