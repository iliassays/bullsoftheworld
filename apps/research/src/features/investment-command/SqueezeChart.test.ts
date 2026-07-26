import { describe, expect, it } from "vitest";

import { buildSqueezeMarkers } from "./SqueezeChart";
import { previewSqueezeMonitor, previewSqueezePath } from "./preview-data";

describe("buildSqueezeMarkers", () => {
  it("keeps repeated setup episodes separately numbered on the chart", () => {
    const entry = previewSqueezeMonitor.families
      .flatMap((family) => family.entries)
      .find((candidate) => candidate.state === "confirmed");
    const fallback = previewSqueezeMonitor.families
      .flatMap((family) => family.entries)
      .at(0);
    const selected = entry ?? fallback;

    expect(selected).toBeDefined();
    const markers = buildSqueezeMarkers(
      previewSqueezePath(selected!.family, selected!.code),
    );
    const labels = markers.map((marker) => marker.text);

    expect(labels).toContain("Discovered #1");
    expect(labels).toContain("Confirmed #1");
    expect(labels).toContain("Discovered #2");
    expect(labels).toContain("Confirmed #2");
  });
});
