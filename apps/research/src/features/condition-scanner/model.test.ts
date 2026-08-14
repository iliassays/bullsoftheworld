import { describe, expect, it } from "vitest";

import type { ConditionCalibration, ConditionCheck } from "./model";
import {
  calibrationFor,
  capTierFromSearch,
  conditionKeyFromSearch,
  formatConditionValue,
  observationFilterFromSearch,
  signedPercent,
} from "./model";

function calibration(
  evidenceMode: "forward" | "reconstructed",
  horizonSessions: 1 | 5 | 20 | 60,
): ConditionCalibration {
  return {
    conditionKey: "trend_alignment",
    conditionVersion: "1.0.0",
    evidenceMode,
    horizonSessions,
    asOfDate: "2026-08-10",
    historyStartDate: "2025-08-10",
    observations: 20,
    matured: 18,
    pending: 2,
    medianReturnPct: -1.25,
    positiveRatePct: 44.4,
    medianExcessReturnPct: -0.8,
    benchmarkObservations: 18,
    averageMaxFavorablePct: 3.1,
    averageMaxAdversePct: -4.2,
    universeSize: 240,
    pointInTimeComplete: false,
    warningText: "Diagnostic only.",
  };
}

describe("condition scanner formatting", () => {
  it("keeps negative values visible instead of presenting every observation as positive", () => {
    expect(signedPercent(-2.345)).toBe("-2.35%");
    expect(signedPercent(0)).toBe("+0.00%");
    expect(signedPercent(null)).toBe("—");
  });

  it("formats actual values according to their registered unit", () => {
    const percentage: ConditionCheck = {
      factKey: "close_vs_ema20_pct",
      label: "Close versus EMA20",
      observed: -1.234,
      expected: "> 0%",
      unit: "percent",
      passed: false,
    };
    const multiple: ConditionCheck = {
      ...percentage,
      factKey: "relative_volume_20",
      observed: 1.5,
      unit: "multiple",
    };

    expect(formatConditionValue(percentage)).toBe("-1.23%");
    expect(formatConditionValue(multiple)).toBe("1.50x");
    expect(formatConditionValue({ ...percentage, observed: null })).toBe("Unavailable");
  });
});

describe("condition calibration selection", () => {
  it("never mixes reconstructed evidence with forward observations", () => {
    const rows = [calibration("reconstructed", 5), calibration("forward", 5)];

    expect(calibrationFor(rows, "forward", 5)?.evidenceMode).toBe("forward");
    expect(calibrationFor(rows, "reconstructed", 5)?.evidenceMode).toBe("reconstructed");
    expect(calibrationFor(rows, "forward", 20)).toBeUndefined();
  });
});

describe("condition scanner URL state", () => {
  it("accepts only registered conditions and tenant-supported cap tiers", () => {
    expect(conditionKeyFromSearch("participation_expansion")).toBe("participation_expansion");
    expect(conditionKeyFromSearch("buy_now")).toBe("trend_alignment");
    expect(capTierFromSearch("small", ["large", "small"])).toBe("small");
    expect(capTierFromSearch("mega", ["large", "small"])).toBe("all");
  });

  it("fails closed to all observations for unknown state values", () => {
    expect(observationFilterFromSearch("new")).toBe("new");
    expect(observationFilterFromSearch("live")).toBe("all");
  });
});
