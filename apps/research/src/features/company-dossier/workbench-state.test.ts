import { describe, expect, it } from "vitest";

import type { DossierPricePoint } from "./model";
import {
  DEFAULT_WORKBENCH_PREFERENCES,
  aggregateWeeklyOverlays,
  aggregateWeeklyPricePoints,
  parseWorkbenchPreferences,
  updateOverlayVisibility,
  weeklyDisplayDateMap,
  workbenchStorageKey,
} from "./workbench-state";

const points: DossierPricePoint[] = [
  { date: "2026-08-03", open: 10, high: 11, low: 9, close: 10.5, volume: 100, benchmarkClose: 100 },
  { date: "2026-08-04", open: 10.5, high: 12, low: 10, close: 11.5, volume: 150, benchmarkClose: 101 },
  { date: "2026-08-07", open: 11.5, high: 13, low: 11, close: 12.5, volume: 200, benchmarkClose: 102 },
  { date: "2026-08-10", open: 13, high: 14, low: 12, close: 13.5, volume: 250, benchmarkClose: 103 },
];

describe("investigation workbench state", () => {
  it("fails closed when saved preferences are malformed or unsupported", () => {
    expect(parseWorkbenchPreferences("not-json")).toEqual(DEFAULT_WORKBENCH_PREFERENCES);
    expect(parseWorkbenchPreferences(JSON.stringify({
      layout: "floating",
      inspector: "oracle",
      overlays: { ema20: false, evidence: "yes" },
    }))).toEqual({
      ...DEFAULT_WORKBENCH_PREFERENCES,
      overlays: { ...DEFAULT_WORKBENCH_PREFERENCES.overlays, ema20: false },
    });
  });

  it("keeps saved layouts isolated by tenant", () => {
    expect(workbenchStorageKey("bullsofdhaka")).not.toBe(workbenchStorageKey("bullsofwallst"));
  });

  it("aggregates daily bars into completed weekly OHLCV without inventing prices", () => {
    expect(aggregateWeeklyPricePoints(points)).toEqual([
      { date: "2026-08-07", open: 10, high: 13, low: 9, close: 12.5, volume: 450, benchmarkClose: 102 },
      { date: "2026-08-10", open: 13, high: 14, low: 12, close: 13.5, volume: 250, benchmarkClose: 103 },
    ]);
  });

  it("uses the last completed session in each week for overlays and markers", () => {
    expect(aggregateWeeklyOverlays([{ key: "ema20", label: "EMA20", points: [
      { date: "2026-08-03", value: 10 },
      { date: "2026-08-07", value: 11 },
      { date: "2026-08-10", value: 12 },
    ] }])[0]?.points).toEqual([
      { date: "2026-08-07", value: 11 },
      { date: "2026-08-10", value: 12 },
    ]);
    expect(weeklyDisplayDateMap(points).get("2026-08-04")).toBe("2026-08-07");
  });

  it("toggles exactly one chart layer", () => {
    const updated = updateOverlayVisibility(DEFAULT_WORKBENCH_PREFERENCES.overlays, "evidence");
    expect(updated.evidence).toBe(false);
    expect(updated.condition).toBe(true);
  });
});
