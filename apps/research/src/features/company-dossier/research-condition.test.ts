import { describe, expect, it } from "vitest";

import type { ResearchConditionWorkbench } from "./model";
import {
  chartMode,
  chartRange,
  chartTimeframe,
  formatObservedValue,
  selectedCondition,
} from "./research-condition";

function workbench(): ResearchConditionWorkbench {
  return {
    methodologyVersion: "research-conditions-v1",
    timeframe: "1d",
    asOfDate: "2026-08-10",
    historyStartDate: "2025-08-10",
    disclaimer: "Research only.",
    overlays: [],
    conditions: [
      {
        key: "trend_alignment",
        version: "1.0.0",
        title: "Trend alignment",
        shortLabel: "T",
        category: "trend",
        state: "not_observed",
        summary: "Not observed.",
        whyItMatters: "Context.",
        limitation: "Not a trade.",
        checks: [],
        transitions: [],
      },
      {
        key: "participation_expansion",
        version: "1.0.0",
        title: "Participation expansion",
        shortLabel: "V",
        category: "volume",
        state: "observed",
        summary: "Observed.",
        whyItMatters: "Context.",
        limitation: "Not a trade.",
        checks: [],
        transitions: [],
      },
    ],
  };
}

describe("research condition context", () => {
  it("prefers a requested condition and otherwise selects an observed condition", () => {
    const data = workbench();

    expect(selectedCondition(data, "trend_alignment").key).toBe("trend_alignment");
    expect(selectedCondition(data, "unknown").key).toBe("participation_expansion");
  });

  it("fails closed to supported chart modes and ranges", () => {
    expect(chartMode("relative")).toBe("relative");
    expect(chartMode("intraday")).toBe("price");
    expect(chartRange("6M")).toBe("6M");
    expect(chartRange("5Y")).toBe("1Y");
    expect(chartTimeframe("1W")).toBe("1W");
    expect(chartTimeframe("1h")).toBe("1D");
  });

  it("formats observed units without hiding negative values", () => {
    expect(formatObservedValue(-1.234, "percent")).toBe("-1.23%");
    expect(formatObservedValue(1.5, "multiple")).toBe("1.50x");
    expect(formatObservedValue(null, "percent")).toBe("Not available");
  });
});
