import { describe, expect, it } from "vitest";

import {
  elapsedBucket,
  experienceStorageKeys,
  filterGlossary,
  readAnalyticsConsent,
  sanitizeAtlasPath,
  shouldShowOrientation,
  workflowStageForPath,
  writeAnalyticsConsent,
  writeOrientationOutcome,
  type AtlasExperienceIdentity,
} from "./model";

class MemoryStorage {
  private readonly values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

const dse: AtlasExperienceIdentity = { tenant: "bullsofdhaka", userId: 29 };
const us: AtlasExperienceIdentity = { tenant: "bullsofwallst", userId: 29 };

describe("Atlas experience state", () => {
  it("isolates onboarding and consent by tenant and user", () => {
    const storage = new MemoryStorage();

    expect(experienceStorageKeys(dse).onboarding).not.toBe(experienceStorageKeys(us).onboarding);
    expect(shouldShowOrientation(dse, storage)).toBe(true);
    expect(shouldShowOrientation(us, storage)).toBe(true);

    writeOrientationOutcome(dse, "completed", storage);
    writeAnalyticsConsent(dse, "granted", storage);

    expect(shouldShowOrientation(dse, storage)).toBe(false);
    expect(readAnalyticsConsent(dse, storage)).toBe("granted");
    expect(shouldShowOrientation(us, storage)).toBe(true);
    expect(readAnalyticsConsent(us, storage)).toBeNull();
  });

  it("treats skipping as a durable one-time orientation outcome", () => {
    const storage = new MemoryStorage();
    writeOrientationOutcome(dse, "skipped", storage);
    expect(shouldShowOrientation(dse, storage)).toBe(false);
  });
});

describe("Atlas help model", () => {
  it("finds terms by name, category, meaning, and misconception", () => {
    expect(filterGlossary("MFE").map((entry) => entry.term)).toContain("MFE");
    expect(filterGlossary("buy signal").map((entry) => entry.term)).toContain("Setup");
    expect(filterGlossary("strategy").length).toBeGreaterThan(1);
    expect(filterGlossary("not-a-real-atlas-term")).toEqual([]);
  });

  it("normalizes routes without exposing ticker symbols or query strings", () => {
    expect(sanitizeAtlasPath("/companies/NXTC?tab=chart")).toBe("/companies/:ticker");
    expect(sanitizeAtlasPath("/setups/")).toBe("/setups");
    expect(sanitizeAtlasPath("/unknown/private/value")).toBe("/other");
  });

  it("maps routes to the real investment workflow", () => {
    expect(workflowStageForPath("/conditions")).toBe("discover");
    expect(workflowStageForPath("/companies/BSC")).toBe("investigate");
    expect(workflowStageForPath("/hypotheses")).toBe("validate");
    expect(workflowStageForPath("/portfolio")).toBe("allocate");
    expect(workflowStageForPath("/memory")).toBe("learn");
  });

  it("uses coarse elapsed buckets instead of recording exact behavior timing", () => {
    expect(elapsedBucket(119_999)).toBe("under_2m");
    expect(elapsedBucket(120_000)).toBe("2_to_10m");
    expect(elapsedBucket(600_000)).toBe("over_10m");
  });
});
