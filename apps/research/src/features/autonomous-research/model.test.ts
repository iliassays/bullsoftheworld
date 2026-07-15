import { describe, expect, it } from "vitest";

import type { ResearchRun } from "../../app/api-client";
import { autonomousDecision, backtestResult } from "./model";

const baseRun: ResearchRun = {
  id: "run-1",
  workspaceId: "workspace-1",
  tenantId: "bullsofdhaka",
  market: "DSE",
  runKind: "deep_research",
  status: "succeeded",
  question: "test",
  code: "BSC",
  parameters: {},
  knowledgeCutoffAt: "2026-07-15T00:00:00Z",
  provider: "deterministic",
  model: "provider-free",
  codeVersion: "v1",
  evidenceSnapshotHash: "abc",
  requestedAt: "2026-07-15T00:00:00Z",
  completedAt: "2026-07-15T00:00:01Z",
  steps: [],
  claims: [],
};

describe("autonomous research JSON adapters", () => {
  it("maps the durable snake-case decision without inventing missing evidence", () => {
    const decision = autonomousDecision({
      ...baseRun,
      parameters: {
        decision: {
          status: "qualified",
          confidence: 0.82,
          headline: "Bounded hypothesis",
          thesis: "Supported",
          counter_thesis: "Fragile",
          invalidation_rules: ["Stop on contradiction"],
          missing_evidence: [],
          limitations: ["EOD only"],
          strategy_key: "dse_reversal_v1",
          lenses: [{ key: "valuation", label: "Valuation", assessment: "balanced", summary: "No edge", fact_keys: ["pe_ratio"] }],
          scenarios: [{ key: "base", title: "Base case", state: "current", condition: "Facts persist", implication: "Monitor", watch_items: ["Next filing"] }],
          next_evidence: [{ priority: "routine", question: "What changed?", reason: "Diff the filing" }],
        },
      },
    });

    expect(decision).toMatchObject({
      status: "qualified",
      confidence: 0.82,
      counterThesis: "Fragile",
      missingEvidence: [],
      lenses: [{ key: "valuation", assessment: "balanced" }],
      scenarios: [{ key: "base", state: "current" }],
      nextEvidence: [{ priority: "routine", question: "What changed?" }],
    });
  });

  it("keeps validation gates separate from performance metrics", () => {
    const result = backtestResult({
      ...baseRun,
      runKind: "hypothesis",
      code: null,
      steps: [{
        ordinal: 2,
        kind: "portfolio_backtest",
        status: "succeeded",
        metrics: {},
        output: {
          engine_version: "engine-v1",
          strategy: { key: "dse_reversal_v1", name: "DSE reversal", description: "test", rebalance_sessions: 5, maximum_positions: 8 },
          risk_policy: { max_position_weight: 0.12 },
          validation_status: "diagnostic",
          failed_gates: ["Inactive history incomplete"],
          metrics: [{ label: "test", sessions: 100, total_return_pct: 4, annualized_return_pct: 10, annualized_volatility_pct: 15, sharpe: 0.6, sortino: 0.9, max_drawdown_pct: 8 }],
          equity_curve: [],
          trades: [],
          risk_interventions: [],
          latest_target_weights: {},
        },
      }],
    });

    expect(result?.validationStatus).toBe("diagnostic");
    expect(result?.failedGates).toEqual(["Inactive history incomplete"]);
    expect(result?.metrics[0]?.label).toBe("test");
  });
});
