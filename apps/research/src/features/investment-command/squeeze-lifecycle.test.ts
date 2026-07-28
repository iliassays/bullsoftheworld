import { describe, expect, it } from "vitest";

import { buildSqueezeLifecycle } from "./squeeze-lifecycle";
import { previewSqueezeMonitor, previewSqueezePath } from "./preview-data";

describe("buildSqueezeLifecycle", () => {
  it("prices only the selected episode's meaningful state transitions", () => {
    const entry = previewSqueezeMonitor.families.flatMap((family) => family.entries).at(0)!;
    const path = previewSqueezePath(entry.family, entry.code);

    const events = buildSqueezeLifecycle(path);

    expect(events.map((event) => event.state)).toEqual([
      "watch",
      "trigger_ready",
      "confirmed",
    ]);
    expect(events[0]!.date).toBe(path.entry.firstDiscoveredOn);
    expect(events[0]!.close).toBe(path.entry.discoveryPrice);
    expect(events[0]!.changeFromDiscoveryPct).toBeNull();
    expect(events[0]!.changeFromPreviousPct).toBeNull();
    expect(events[1]!.close).not.toBeNull();
    expect(events[1]!.changeFromDiscoveryPct).not.toBeNull();
    expect(events[1]!.changeFromPreviousPct).not.toBeNull();
  });

  it("omits bookkeeping none transitions from the visible lifecycle", () => {
    const entry = previewSqueezeMonitor.families.flatMap((family) => family.entries).at(0)!;
    const path = previewSqueezePath(entry.family, entry.code);
    path.stateHistory.push({
      date: path.points.at(-1)!.date,
      state: "none",
      previousState: "confirmed",
      reason: "Episode closed.",
      episodeNumber: path.discoveryNumber,
      isCurrentEpisode: true,
    });

    expect(buildSqueezeLifecycle(path)).toHaveLength(3);
  });
});
