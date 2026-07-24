import { describe, expect, it } from "vitest";

import type {
  DecisionEvent,
  InvestmentOperatingView,
  ShadowPortfolio,
} from "../../app/api-client";
import type { AutonomousDecision } from "../autonomous-research/model";
import { buildDecisionTicket } from "./decision-ticket";

const decision: AutonomousDecision = {
  status: "qualified",
  confidence: 0.72,
  evidenceCompletenessPct: 80,
  thesisStrength: "moderate",
  outcomeCalibration: "uncalibrated",
  headline: "Official evidence supports further investigation.",
  thesis: "Thesis",
  counterThesis: "Counter-thesis",
  invalidationRules: ["Close below registered support invalidates the setup."],
  missingEvidence: [],
  limitations: [],
  strategyKey: "dse_reversal_v1",
  lenses: [],
  scenarios: [],
  nextEvidence: [],
};

function event(overrides: Partial<DecisionEvent>): DecisionEvent {
  return {
    id: "event-1",
    portfolioId: "portfolio-1",
    snapshotId: "snapshot-1",
    correlationId: "correlation-1",
    sequence: 1,
    eventKey: "event-key",
    causedByEventKey: null,
    eventType: "target",
    eventState: "intended",
    code: "AAA",
    effectiveDate: "2026-07-20",
    payload: {},
    payloadHash: "hash",
    recordedAt: "2026-07-20T18:00:00Z",
    ...overrides,
  };
}

function portfolio(
  positions: ShadowPortfolio["snapshots"][number]["positions"],
  targetWeights: Record<string, number>,
): ShadowPortfolio {
  return {
    id: "portfolio-1",
    workspaceId: "workspace-1",
    tenantId: "bullsofdhaka",
    market: "DSE",
    sourceRunId: "run-1",
    name: "Forward shadow book",
    strategyKey: "dse_reversal_v1",
    status: "active",
    initialCapital: 1_000_000,
    inceptionDate: "2026-07-01",
    lastEvaluatedOn: "2026-07-20",
    configuration: {},
    snapshots: [{
      id: "snapshot-1",
      asOfDate: "2026-07-20",
      sessionNumber: 10,
      nav: 1_000_000,
      cash: 900_000,
      benchmarkNav: 1_005_000,
      peakNav: 1_010_000,
      grossExposurePct: 10,
      drawdownPct: 1,
      cumulativeFees: 100,
      cumulativeTurnover: 10,
      positions,
      targetWeights,
      trades: [],
      riskInterventions: [],
    }],
  };
}

function operatingView(events: DecisionEvent[]): InvestmentOperatingView {
  return {
    workspaceId: "workspace-1",
    tenantId: "bullsofdhaka",
    market: "DSE",
    generatedAt: "2026-07-20T18:00:00Z",
    mandate: {
      id: "mandate-1",
      workspaceId: "workspace-1",
      tenantId: "bullsofdhaka",
      market: "DSE",
      version: 1,
      status: "active",
      objective: "Test",
      benchmarkKey: "DSEX",
      maxGrossExposurePct: 85,
      minCashReservePct: 15,
      maxPositionWeightPct: 12,
      maxSectorWeightPct: 30,
      maxAdvParticipationPct: 2,
      portfolioDrawdownBrakePct: 15,
      stressLossLimitPct: 12,
      specificationHash: "hash",
      effectiveAt: "2026-07-01T00:00:00Z",
      supersededAt: null,
    },
    trials: [],
    portfolios: [{
      portfolioId: "portfolio-1",
      asOfDate: "2026-07-20",
      mandate: {} as InvestmentOperatingView["mandate"],
      mandateVersion: 1,
      mandateBinding: "pinned",
      risk: {
        grossExposurePct: 10,
        cashReservePct: 90,
        largestPositionPct: 10,
        largestSectorPct: 10,
        concentrationHhi: 1,
        effectivePositions: 1,
        weightedAverageCorrelation: null,
        maximumPairCorrelation: null,
        maximumExitDays: 1,
        limitChecks: [],
        stressScenarios: [],
        breachedLimits: [],
        dataQualityNotes: [],
      },
      attribution: {
        portfolioReturnPct: 0,
        benchmarkReturnPct: 0,
        excessReturnPct: 0,
        components: [],
        rejectedActions: 0,
        methodologyVersion: "v1",
      },
      recentEvents: events,
    }],
  };
}

const baseInput = {
  ticker: "AAA",
  currentPrice: 100,
  evidenceFreshness: "fresh" as const,
  candidateInvalidation: "Candidate invalidation",
  capacity: "moderate",
  exitDays: 1.2,
  decision,
};

describe("buildDecisionTicket", () => {
  it("never converts a qualified research conclusion into a portfolio target", () => {
    const result = buildDecisionTicket({
      ...baseInput,
      portfolios: [],
      operatingView: undefined,
    });

    expect(result.action).toBe("investigate");
    expect(result.targetWeightPct).toBeNull();
    expect(result.execution).toContain("No order is implied");
  });

  it("shows a registered target only when an active shadow book carries it", () => {
    const target = event({ payload: { target_weight: 0.1, action: "entry" } });
    const result = buildDecisionTicket({
      ...baseInput,
      portfolios: [portfolio({}, { AAA: 0.1 })],
      operatingView: operatingView([target]),
    });

    expect(result.action).toBe("target");
    expect(result.source).toBe("portfolio_ledger");
    expect(result.targetWeightPct).toBe(10);
    expect(result.execution).toContain("next observable session open");
  });

  it("distinguishes a held position from its target and reports average cost", () => {
    const fill = event({
      eventType: "fill",
      eventState: "executed",
      sequence: 2,
      payload: { side: "buy", fill_price: 92.5 },
    });
    const result = buildDecisionTicket({
      ...baseInput,
      portfolios: [portfolio({ AAA: { shares: 1_000, average_cost: 92.5 } }, { AAA: 0.1 })],
      operatingView: operatingView([fill]),
    });

    expect(result.action).toBe("held");
    expect(result.currentWeightPct).toBe(10);
    expect(result.averageCost).toBe(92.5);
    expect(result.latestFillPrice).toBe(92.5);
  });

  it("surfaces a zero target on an open position as an exit, not a hold", () => {
    const target = event({ payload: { target_weight: 0, action: "exit" } });
    const result = buildDecisionTicket({
      ...baseInput,
      portfolios: [portfolio({ AAA: { shares: 1_000, average_cost: 92.5 } }, {})],
      operatingView: operatingView([target]),
    });

    expect(result.action).toBe("exit");
    expect(result.targetWeightPct).toBe(0);
  });
});
