import { describe, expect, it } from "vitest";

import { CHART_RANGES, buildConditionMarkers } from "./DossierChart";
import type { ResearchConditionEvaluation } from "./model";

function condition(): ResearchConditionEvaluation {
  return {
    key: "trend_alignment",
    version: "1.0.0",
    title: "Trend alignment",
    shortLabel: "T",
    category: "trend",
    state: "observed",
    summary: "Observed.",
    whyItMatters: "Context.",
    limitation: "Not a strategy.",
    checks: [],
    transitions: Array.from({ length: 15 }, (_, index) => ({
      date: `2026-07-${String(index + 1).padStart(2, "0")}`,
      close: 100 + index,
      sequence: index + 1,
    })),
  };
}

describe("buildConditionMarkers", () => {
  it("keeps chart range controls distinct from timeframe controls", () => {
    expect(CHART_RANGES).toEqual(["3M", "6M", "1Y"]);
  });

  it("shows only visible observations and caps chart annotation noise", () => {
    const availableDates = Array.from(
      { length: 15 },
      (_, index) => `2026-07-${String(index + 1).padStart(2, "0")}`,
    );

    const markers = buildConditionMarkers(availableDates, condition());

    expect(markers).toHaveLength(12);
    expect(markers[0]?.text).toBe("T4");
    expect(markers.at(-1)?.text).toBe("T15");
  });

  it("does not move a transition onto a date that was not observed", () => {
    const markers = buildConditionMarkers(["2026-07-15"], {
      ...condition(),
      transitions: [{ date: "2026-07-14", close: 100, sequence: 1 }],
    });

    expect(markers).toEqual([]);
  });

  it("places a daily transition on its completed weekly display bar", () => {
    const markers = buildConditionMarkers(
      ["2026-08-07"],
      {
        ...condition(),
        transitions: [{ date: "2026-08-04", close: 100, sequence: 7 }],
      },
      new Map([
        ["2026-08-03", "2026-08-07"],
        ["2026-08-04", "2026-08-07"],
        ["2026-08-07", "2026-08-07"],
      ]),
    );

    expect(markers).toEqual([
      expect.objectContaining({ time: "2026-08-07", text: "T7" }),
    ]);
  });
});
