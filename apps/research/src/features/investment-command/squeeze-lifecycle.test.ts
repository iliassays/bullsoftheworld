import { describe, expect, it } from "vitest";

import {
  buildSqueezeLifecycle,
  buildSqueezeLifecycleEpisodes,
} from "./squeeze-lifecycle";
import { previewSqueezeMonitor, previewSqueezePath } from "./preview-data";

describe("buildSqueezeLifecycle", () => {
  it("prices only the selected episode's meaningful state transitions", () => {
    const entry = previewSqueezeMonitor.families.flatMap((family) => family.entries).at(0)!;
    const path = previewSqueezePath(entry.family, entry.code);

    const events = buildSqueezeLifecycle(path);

    expect(events.map((event) => event.state)).toEqual(
      entry.state === "confirmed"
        ? ["watch", "trigger_ready", "confirmed"]
        : ["watch", "forming", "trigger_ready"],
    );
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
      evidenceMode: "forward",
      methodologyVersion: "squeeze-monitor-v3",
      episodeNumber: path.discoveryNumber,
      isCurrentEpisode: true,
    });

    expect(buildSqueezeLifecycle(path)).toHaveLength(3);
  });

  it("keeps earlier episodes separate and resets each price baseline", () => {
    const entry = previewSqueezeMonitor.families.flatMap((family) => family.entries).at(0)!;
    const path = previewSqueezePath(entry.family, entry.code);

    const episodes = buildSqueezeLifecycleEpisodes(path);

    expect(episodes).toHaveLength(2);
    expect(episodes[0]!.isCurrentEpisode).toBe(false);
    expect(episodes[0]!.events[0]!.changeFromDiscoveryPct).toBeNull();
    expect(episodes[1]!.isCurrentEpisode).toBe(true);
    expect(episodes[1]!.events[0]!.changeFromDiscoveryPct).toBeNull();
    expect(episodes[1]!.events[0]!.episodeNumber).toBe(path.discoveryNumber);
  });

  it("preserves a direct confirmation without inventing earlier phases", () => {
    const entry = previewSqueezeMonitor.families.flatMap((family) => family.entries).at(0)!;
    const path = previewSqueezePath(entry.family, entry.code);
    const observationDate = path.points.at(-1)!.date;
    path.entry.firstDiscoveredOn = observationDate;
    path.entry.firstConfirmedOn = observationDate;
    path.entry.discoveryPrice = path.points.at(-1)!.close;
    path.stateHistory = [
      ...path.stateHistory.filter((marker) => !marker.isCurrentEpisode),
      {
        date: observationDate,
        state: "confirmed",
        previousState: "none",
        reason: "The first retained observation met the confirmation rule.",
        evidenceMode: "forward",
        methodologyVersion: "squeeze-monitor-v1",
        episodeNumber: path.discoveryNumber,
        isCurrentEpisode: true,
      },
    ];

    const events = buildSqueezeLifecycle(path);

    expect(events).toHaveLength(1);
    expect(events[0]!.state).toBe("confirmed");
    expect(events[0]!.previousState).toBe("none");
    expect(events[0]!.isEpisodeStart).toBe(true);
    expect(events[0]!.changeFromDiscoveryPct).toBeNull();
  });
});
