import { describe, expect, it } from "vitest";

import { factorReading, METRIC_GUIDANCE } from "./guidance";

describe("company dossier guidance", () => {
  it("keeps factor interpretation directional without presenting return forecasts", () => {
    expect(factorReading("quality", 72)).toBe("Stronger than midpoint");
    expect(factorReading("momentum", 51)).toBe("Near model midpoint");
    expect(factorReading("value", 30)).toBe("Limited support");
  });

  it("makes the asymmetric risk qualification gates explicit", () => {
    expect(factorReading("risk", 40)).toBe("Lower burden");
    expect(factorReading("risk", 60)).toBe("Elevated burden");
    expect(factorReading("risk", 80)).toBe("Blocks qualification");
    expect(factorReading("risk", 90)).toBe("Hard rejection band");
  });

  it("uses registered reference thresholds rather than universal good-value claims", () => {
    expect(METRIC_GUIDANCE.relativeVolume.reference).toContain("1.00x is normal");
    expect(METRIC_GUIDANCE.peVsSector.reference).toContain("1.00x is the sector median");
    expect(METRIC_GUIDANCE.dividendYield.reference).toContain("no universal ideal yield");
  });
});
