import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { researchApi } from "../../app/api-client";
import { isResearchPreview, researchDeployment } from "../../app/deployment";
import {
  previewAutomationPolicy,
  previewInvestmentOperatingView,
  previewInvestmentMandate,
  previewResearchRuns,
  previewShadowPortfolios,
  previewStrategies,
  previewStrategyDataReadiness,
} from "./preview-data";

export function useStrategyCatalog(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["research", "strategies", workspaceId],
    queryFn: () => isResearchPreview ? previewStrategies : researchApi.strategies(workspaceId!),
    enabled: Boolean(workspaceId),
    staleTime: 60_000,
  });
}

export function useResearchRuns(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["research", "runs", workspaceId],
    queryFn: () => isResearchPreview ? previewResearchRuns : researchApi.runs(workspaceId!),
    enabled: Boolean(workspaceId),
    refetchInterval: 15_000,
  });
}

export function useResearchRun(workspaceId: string | undefined, runId: string | undefined) {
  return useQuery({
    queryKey: ["research", "run", workspaceId, runId],
    queryFn: () => isResearchPreview
      ? previewResearchRuns.find((run) => run.id === runId) ?? Promise.reject(new Error("Preview run not found"))
      : researchApi.run(workspaceId!, runId!),
    enabled: Boolean(workspaceId && runId),
  });
}

export function useStrategyDataReadiness(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["research", "strategy-data-readiness", workspaceId],
    queryFn: () => isResearchPreview
      ? previewStrategyDataReadiness
      : researchApi.strategyDataReadiness(workspaceId!),
    enabled: Boolean(workspaceId && researchDeployment.market === "DSE"),
    refetchInterval: 30_000,
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
    queryFn: () => isResearchPreview
      ? previewShadowPortfolios
      : researchApi.shadowPortfolios(workspaceId!),
    enabled: Boolean(workspaceId),
    refetchInterval: 30_000,
  });
}

export function useInvestmentOperatingView(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["research", "investment-operating-view", workspaceId],
    queryFn: () => isResearchPreview
      ? previewInvestmentOperatingView
      : researchApi.investmentOperatingView(workspaceId!),
    enabled: Boolean(workspaceId),
    refetchInterval: 30_000,
  });
}

export function useConfigureInvestmentMandate(workspaceId: string | undefined) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Parameters<typeof researchApi.configureInvestmentMandate>[1]) => {
      if (!isResearchPreview) return researchApi.configureInvestmentMandate(workspaceId!, payload);
      return Promise.resolve({
        ...previewInvestmentMandate,
        id: "00000000-0000-0000-0000-000000000602",
        version: previewInvestmentMandate.version + 1,
        objective: payload.objective,
        benchmarkKey: payload.benchmark_key,
        maxGrossExposurePct: payload.max_gross_exposure_pct,
        minCashReservePct: payload.min_cash_reserve_pct,
        maxPositionWeightPct: payload.max_position_weight_pct,
        maxSectorWeightPct: payload.max_sector_weight_pct,
        maxAdvParticipationPct: payload.max_adv_participation_pct,
        portfolioDrawdownBrakePct: payload.portfolio_drawdown_brake_pct,
        stressLossLimitPct: payload.stress_loss_limit_pct,
        effectiveAt: new Date().toISOString(),
      });
    },
    onSuccess: (mandate) => {
      if (isResearchPreview) {
        client.setQueryData(
          ["research", "investment-operating-view", workspaceId],
          { ...previewInvestmentOperatingView, mandate },
        );
        return;
      }
      void client.invalidateQueries({
        queryKey: ["research", "investment-operating-view", workspaceId],
      });
    },
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
    queryFn: () => isResearchPreview
      ? previewAutomationPolicy
      : researchApi.automationPolicy(workspaceId!),
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
