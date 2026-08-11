import { describe, expect, it } from "vitest";

import { previewSqueezeMonitor, previewSqueezePath } from "./preview-data";

describe("investment command preview setup fixtures", () => {
  it("keeps the selected row, lifecycle endpoint, and chart close coherent", () => {
    for (const family of previewSqueezeMonitor.families) {
      for (const entry of family.entries) {
        const path = previewSqueezePath(family.family, entry.code);
        const currentEvents = path.stateHistory.filter((event) => event.isCurrentEpisode);
        const finalEvent = currentEvents.at(-1);
        const finalPoint = path.points.at(-1);

        expect(path.entry.family).toBe(family.family);
        expect(path.entry.code).toBe(entry.code);
        expect(path.entry.state).toBe(entry.state);
        expect(path.entry.asOfPrice).toBe(entry.asOfPrice);
        expect(finalEvent?.state).toBe(entry.state);
        expect(finalEvent?.date).toBe(entry.asOfDate);
        expect(finalPoint?.date).toBe(entry.asOfDate);
        expect(finalPoint?.close).toBe(entry.asOfPrice);
      }
    }
  });

  it("uses prices compatible with the preview state claims", () => {
    for (const family of previewSqueezeMonitor.families) {
      for (const entry of family.entries) {
        if (entry.asOfPrice === null || entry.triggerPrice === null) {
          throw new Error("Preview setup rows require as-of and trigger prices");
        }
        if (entry.state === "confirmed") {
          expect(entry.asOfPrice).toBeGreaterThan(entry.triggerPrice);
          expect(entry.confirmationPrice).toBe(entry.asOfPrice);
        } else if (entry.state === "trigger_ready") {
          const distanceToTrigger = (entry.triggerPrice - entry.asOfPrice) / entry.triggerPrice;
          expect(distanceToTrigger).toBeGreaterThanOrEqual(0);
          expect(distanceToTrigger).toBeLessThanOrEqual(0.03);
          expect(entry.confirmationPrice).toBeNull();
        }
      }
    }
  });
});
