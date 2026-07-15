import { describe, expect, it } from "vitest";

import { demoQueueSnapshot } from "./preview-data";
import { filterResearchQueue, summarizeResearchQueue } from "./model";

describe("filterResearchQueue", () => {
  it("combines workflow status and text filters", () => {
    const result = filterResearchQueue(demoQueueSnapshot.candidates, {
      status: "new_evidence",
      capTier: "all",
      query: "biopharma",
    });

    expect(result.map((candidate) => candidate.ticker)).toEqual(["AEON"]);
  });

  it("searches research reason in addition to identity fields", () => {
    const result = filterResearchQueue(demoQueueSnapshot.candidates, {
      status: "all",
      capTier: "all",
      query: "runway",
    });

    expect(result.map((candidate) => candidate.ticker)).toContain("NXTC");
  });

  it("enforces capitalization mandate in the domain filter", () => {
    const result = filterResearchQueue(demoQueueSnapshot.candidates, {
      status: "all",
      capTier: "small",
      query: "",
    });

    expect(result.map((candidate) => candidate.ticker)).toEqual(["SEAPEARL", "ITC", "QTTB"]);
  });
});

describe("summarizeResearchQueue", () => {
  it("derives workflow counts without embedding them in presentation code", () => {
    const summary = summarizeResearchQueue(demoQueueSnapshot.candidates);

    expect(summary.total).toBe(demoQueueSnapshot.candidates.length);
    expect(summary.newEvidence).toBeGreaterThan(0);
    expect(summary.needsReview).toBeGreaterThan(0);
    expect(summary.evidenceGaps).toBeGreaterThan(0);
  });
});
