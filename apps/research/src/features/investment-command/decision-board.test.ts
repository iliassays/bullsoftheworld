import { describe, expect, it } from "vitest";

import type { DecisionCandidate, DecisionCandidateState } from "../../app/api-client";
import {
  decisionStateLabel,
  matchesCapTier,
  matchesDecisionFilter,
} from "./decision-board";

function candidate(state: DecisionCandidateState): DecisionCandidate {
  return {
    id: state,
    portfolioId: "portfolio",
    portfolioName: "Book",
    strategyKey: "test",
    strategyName: "Test strategy",
    direction: "long",
    horizon: "swing",
    expectedHolding: "Approximately 5-20 completed sessions",
    code: "TEST",
    company: "Test Company",
    capTier: "small",
    state,
    evidenceMode: "forward",
    asOfDate: "2026-07-23",
    firstDiscoveredOn: "2026-07-20",
    isNew: false,
    discoveryPrice: 100,
    asOfPrice: 105,
    returnSinceDiscoveryPct: 5,
    maxFavorablePct: 8,
    maxAdversePct: -3,
    sessionsSinceDiscovery: 4,
    targetWeightPct: 8,
    positionWeightPct: 0,
    latestFillSide: null,
    latestFillPrice: null,
    latestFillDate: null,
    riskReferencePrice: 100,
    invalidationPrice: 90,
    planningObjectivePrice: 120,
    planningRewardRisk: 2,
    exitPolicy: "10% position stop.",
    headline: "Test",
    story: "Test",
    riskNotes: [],
  };
}

describe("decision board filters", () => {
  it("keeps blocked orders with entries and closed positions with exits", () => {
    expect(matchesDecisionFilter(candidate("ready"), "entries")).toBe(true);
    expect(matchesDecisionFilter(candidate("blocked"), "entries")).toBe(true);
    expect(matchesDecisionFilter(candidate("manage"), "positions")).toBe(true);
    expect(matchesDecisionFilter(candidate("exit"), "exits")).toBe(true);
    expect(matchesDecisionFilter(candidate("closed"), "exits")).toBe(true);
    expect(matchesDecisionFilter(candidate("manage"), "entries")).toBe(false);
  });

  it("uses action language rather than implying every target was filled", () => {
    expect(decisionStateLabel("ready")).toBe("Entry target");
    expect(decisionStateLabel("manage")).toBe("Active position");
    expect(decisionStateLabel("blocked")).toBe("Blocked");
  });

  it("filters decisions by the archived capitalization classification", () => {
    expect(matchesCapTier(candidate("ready"), "all")).toBe(true);
    expect(matchesCapTier(candidate("ready"), "small")).toBe(true);
    expect(matchesCapTier(candidate("ready"), "large")).toBe(false);
  });
});
