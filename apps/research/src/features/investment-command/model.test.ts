import { describe, expect, it } from "vitest";

import type { ResearchRun, ShadowPortfolio } from "../../app/api-client";
import type { CatalystEvent } from "../catalyst-calendar/model";
import {
  buildDecisionActions,
  latestLifecycleRun,
  summarizeStrategyBooks,
  upcomingCatalysts,
} from "./model";

const portfolio: ShadowPortfolio = {
  id: "book-1",
  workspaceId: "workspace-1",
  tenantId: "bullsofdhaka",
  market: "DSE",
  sourceRunId: "run-0",
  name: "Diagnostic book",
  strategyKey: "dse_reversal_v1",
  status: "active",
  initialCapital: 1000,
  inceptionDate: "2026-07-15",
  lastEvaluatedOn: "2026-07-18",
  configuration: { promotion: { status: "diagnostic" } },
  snapshots: [
    {
      id: "snapshot-1",
      asOfDate: "2026-07-17",
      sessionNumber: 1,
      nav: 1000,
      cash: 1000,
      benchmarkNav: 1000,
      peakNav: 1000,
      grossExposurePct: 0,
      drawdownPct: 0,
      cumulativeFees: 0,
      cumulativeTurnover: 0,
      positions: {},
      targetWeights: {},
      trades: [],
      riskInterventions: [],
    },
    {
      id: "snapshot-2",
      asOfDate: "2026-07-18",
      sessionNumber: 2,
      nav: 1010,
      cash: 800,
      benchmarkNav: 1005,
      peakNav: 1020,
      grossExposurePct: 20,
      drawdownPct: 0.98,
      cumulativeFees: 1,
      cumulativeTurnover: 20,
      positions: { AAA: { shares: 10, average_cost: 20 } },
      targetWeights: { BBB: 0.1 },
      trades: [{ code: "AAA" }],
      riskInterventions: [{ rule: "cash_constraint" }],
    },
  ],
};

const run: ResearchRun = {
  id: "run-1",
  workspaceId: "workspace-1",
  tenantId: "bullsofdhaka",
  market: "DSE",
  runKind: "lifecycle",
  status: "succeeded",
  question: "test",
  code: null,
  parameters: {},
  knowledgeCutoffAt: "2026-07-18T12:00:00Z",
  provider: null,
  model: null,
  codeVersion: "test",
  evidenceSnapshotHash: null,
  requestedAt: "2026-07-18T12:00:00Z",
  completedAt: "2026-07-18T12:05:00Z",
  claims: [],
  steps: [
    {
      ordinal: 1,
      kind: "forward_shadow_reconciliation",
      status: "succeeded",
      metrics: {},
      output: {
        target_changes: [{
          code: "BBB",
          previous_weight: 0,
          target_weight: 0.1,
          action: "entry_target",
          date: "2026-07-18",
          session_number: 2,
        }],
        new_executions: [{
          code: "AAA",
          side: "buy",
          quantity: 10,
          fill_price: 20,
          gross_value: 200,
          fee: 1,
          date: "2026-07-18",
          session_number: 2,
        }],
        new_risk_interventions: [{ rule: "cash_constraint" }],
      },
    },
  ],
};

describe("investment command model", () => {
  it("keeps queued targets separate from completed positions and performance", () => {
    const [book] = summarizeStrategyBooks([portfolio]);

    expect(book!.positionCount).toBe(1);
    expect(book!.queuedEntries).toBe(1);
    expect(book!.queuedExits).toBe(1);
    expect(book!.netReturnPct).toBeCloseTo(1);
    expect(book!.excessReturnPct).toBeCloseTo(0.5);
    expect(book!.promotionStatus).toBe("diagnostic");
  });

  it("orders risk review before future targets and completed fills", () => {
    const actions = buildDecisionActions(run, summarizeStrategyBooks([portfolio]));

    expect(actions.map((action) => action.state)).toEqual([
      "review",
      "next_session",
      "completed",
    ]);
    expect(actions[1]!.title).toBe("Entry target formed");
  });

  it("selects the newest lifecycle rather than a newer company run", () => {
    const companyRun = { ...run, id: "company", runKind: "deep_research", completedAt: "2026-07-19T12:00:00Z" };
    const oldLifecycle = { ...run, id: "old", completedAt: "2026-07-17T12:00:00Z" };

    expect(latestLifecycleRun([companyRun, oldLifecycle, run])?.id).toBe("run-1");
  });

  it("shows only scheduled future catalysts in chronological order", () => {
    const event = (id: string, date: string, status: CatalystEvent["status"]): CatalystEvent => ({
      id,
      code: id,
      eventType: "board_meeting",
      title: id,
      timingKind: "confirmed",
      confirmedDate: date,
      windowStart: null,
      windowEnd: null,
      status,
      confidence: "official_confirmed",
      sourceType: "dse",
      sourceRef: id,
      sourceUrl: null,
      knownAt: "2026-07-18T00:00:00Z",
      expectedEvidence: null,
      details: null,
    });

    expect(upcomingCatalysts([
      event("later", "2026-07-24", "scheduled"),
      event("past", "2026-07-17", "scheduled"),
      event("first", "2026-07-20", "scheduled"),
      event("cancelled", "2026-07-19", "cancelled"),
    ], "2026-07-18").map((item) => item.id)).toEqual(["first", "later"]);
  });
});
