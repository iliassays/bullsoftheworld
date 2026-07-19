import type {
  AutomationPolicy,
  ResearchRun,
  ShadowPortfolio,
} from "../../app/api-client";
import type { CatalystEvent } from "../catalyst-calendar/model";
import { anchorDate } from "../catalyst-calendar/model";
import type { ResearchCandidate } from "../research-queue/model";
import { lifecycleRunDelta } from "../autonomous-research/model";

export interface StrategyBookSummary {
  id: string;
  name: string;
  strategyKey: string;
  status: ShadowPortfolio["status"];
  asOfDate: string | null;
  nav: number;
  cash: number;
  netReturnPct: number;
  benchmarkReturnPct: number;
  excessReturnPct: number;
  grossExposurePct: number;
  drawdownPct: number;
  positionCount: number;
  queuedEntries: number;
  queuedExits: number;
  latestExecutions: number;
  latestRiskInterventions: number;
  promotionStatus: string;
}

export interface DecisionAction {
  id: string;
  kind: "risk" | "target" | "execution";
  state: "review" | "next_session" | "completed";
  code: string | null;
  title: string;
  detail: string;
  date: string | null;
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function promotionStatus(portfolio: ShadowPortfolio): string {
  const promotion = record(portfolio.configuration.promotion);
  return typeof promotion?.status === "string" ? promotion.status : "not evaluated";
}

export function summarizeStrategyBooks(
  portfolios: readonly ShadowPortfolio[],
): StrategyBookSummary[] {
  return portfolios.map((portfolio) => {
    const initial = portfolio.snapshots[0];
    const latest = portfolio.snapshots[portfolio.snapshots.length - 1];
    const positions = latest?.positions ?? {};
    const targets: Record<string, number> = latest?.targetWeights ?? {};
    const queuedEntries = Object.entries(targets).filter(
      ([code, target]) => target > 0 && !positions[code],
    ).length;
    const queuedExits = Object.keys(positions).filter(
      (code) => (targets[code] ?? 0) <= 0,
    ).length;
    const netReturnPct = latest && initial && initial.nav > 0
      ? (latest.nav / initial.nav - 1) * 100
      : 0;
    const benchmarkReturnPct = latest && initial && initial.benchmarkNav > 0
      ? (latest.benchmarkNav / initial.benchmarkNav - 1) * 100
      : 0;

    return {
      id: portfolio.id,
      name: portfolio.name,
      strategyKey: portfolio.strategyKey,
      status: portfolio.status,
      asOfDate: latest?.asOfDate ?? null,
      nav: latest?.nav ?? portfolio.initialCapital,
      cash: latest?.cash ?? portfolio.initialCapital,
      netReturnPct,
      benchmarkReturnPct,
      excessReturnPct: netReturnPct - benchmarkReturnPct,
      grossExposurePct: latest?.grossExposurePct ?? 0,
      drawdownPct: latest?.drawdownPct ?? 0,
      positionCount: Object.keys(positions).length,
      queuedEntries,
      queuedExits,
      latestExecutions: latest?.trades.length ?? 0,
      latestRiskInterventions: latest?.riskInterventions.length ?? 0,
      promotionStatus: promotionStatus(portfolio),
    };
  });
}

export function latestLifecycleRun(runs: readonly ResearchRun[]): ResearchRun | undefined {
  return [...runs]
    .filter((run) => run.runKind === "lifecycle")
    .sort((left, right) =>
      (right.completedAt ?? right.requestedAt).localeCompare(
        left.completedAt ?? left.requestedAt,
      ),
    )[0];
}

export function buildDecisionActions(
  run: ResearchRun | undefined,
  books: readonly StrategyBookSummary[],
): DecisionAction[] {
  const delta = lifecycleRunDelta(run);
  const actions: DecisionAction[] = [];

  for (const target of delta.targetChanges) {
    const verb = target.action === "entry_target"
      ? "Entry"
      : target.action === "exit_target"
        ? "Exit"
        : target.action === "increase_target"
          ? "Increase"
          : "Reduce";
    actions.push({
      id: `target:${target.sessionNumber}:${target.code}:${target.action}`,
      kind: "target",
      state: "next_session",
      code: target.code,
      title: `${verb} target formed`,
      detail: `${(target.previousWeight * 100).toFixed(1)}% to ${(target.targetWeight * 100).toFixed(1)}% portfolio weight. This is an instruction for the next eligible paper fill, not a completed trade.`,
      date: target.date || null,
    });
  }

  for (const execution of delta.executions) {
    actions.push({
      id: `execution:${execution.id}`,
      kind: "execution",
      state: "completed",
      code: execution.code,
      title: `${execution.side === "buy" ? "Buy" : "Sell"} paper fill completed`,
      detail: `${execution.quantity.toLocaleString("en-US")} shares at ${execution.fillPrice.toFixed(2)}, including a recorded fee of ${execution.fee.toFixed(2)}.`,
      date: execution.date,
    });
  }

  const riskCount = Math.max(
    delta.riskInterventions,
    books.reduce((total, book) => total + book.latestRiskInterventions, 0),
  );
  if (riskCount > 0) {
    actions.push({
      id: `risk:${run?.id ?? "latest"}`,
      kind: "risk",
      state: "review",
      code: null,
      title: `${riskCount} risk ${riskCount === 1 ? "intervention requires" : "interventions require"} review`,
      detail: "A constraint changed or rejected the desired portfolio. Open the risk ledger before interpreting strategy performance.",
      date: run?.completedAt?.slice(0, 10) ?? null,
    });
  }

  const stateOrder: Record<DecisionAction["state"], number> = {
    review: 0,
    next_session: 1,
    completed: 2,
  };
  return actions.sort((left, right) =>
    stateOrder[left.state] - stateOrder[right.state] ||
    (right.date ?? "").localeCompare(left.date ?? "") ||
    (left.code ?? "").localeCompare(right.code ?? ""),
  );
}

export function researchInbox(
  candidates: readonly ResearchCandidate[],
  limit = 5,
): ResearchCandidate[] {
  return [...candidates]
    .filter((candidate) => candidate.status !== "monitoring")
    .sort((left, right) => right.priority - left.priority)
    .slice(0, limit);
}

export function upcomingCatalysts(
  events: readonly CatalystEvent[],
  today: string,
  limit = 5,
): CatalystEvent[] {
  return [...events]
    .filter((event) => event.status === "scheduled" && anchorDate(event) >= today)
    .sort((left, right) =>
      anchorDate(left).localeCompare(anchorDate(right)) || left.code.localeCompare(right.code),
    )
    .slice(0, limit);
}

export function automationHeadline(policy: AutomationPolicy | null | undefined): string {
  if (!policy) return "Automation is not configured";
  if (!policy.enabled) return "Post-close process is paused";
  if (policy.lastRunStatus === "failed") return "Last post-close process failed";
  if (policy.lastRunStatus === "running" || policy.lastRunStatus === "queued") {
    return "Post-close process is running";
  }
  return "Post-close process is active";
}
