import { describe, expect, it } from "vitest";

import { buildSqueezeMarkers } from "./SqueezeChart";
import { previewSqueezeMonitor, previewSqueezePath } from "./preview-data";

describe("buildSqueezeMarkers", () => {
  it("shows the current episode and recent prior episodes that confirmed", () => {
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

    expect(labels).toContain("D1");
    expect(labels).toContain("C1");
    expect(labels).toContain("D2");
    expect(labels).toContain("C2");
    expect(labels).toContain("T2");
  });

  it("does not render every unconfirmed historical episode", () => {
    const selected = previewSqueezeMonitor.families.flatMap((family) => family.entries).at(0)!;
    const path = previewSqueezePath(selected.family, selected.code);
    path.discoveryNumber = 5;
    path.stateHistory = [
      {
        date: "2026-01-01",
        state: "watch",
        previousState: "none",
        reason: "old watch",
        evidenceMode: "reconstructed",
        methodologyVersion: "squeeze-monitor-v3",
        episodeNumber: 1,
        isCurrentEpisode: false,
      },
      {
        date: "2026-02-01",
        state: "forming",
        previousState: "none",
        reason: "old forming",
        evidenceMode: "reconstructed",
        methodologyVersion: "squeeze-monitor-v3",
        episodeNumber: 2,
        isCurrentEpisode: false,
      },
      {
        date: "2026-03-01",
        state: "confirmed",
        previousState: "forming",
        reason: "confirmed",
        evidenceMode: "reconstructed",
        methodologyVersion: "squeeze-monitor-v3",
        episodeNumber: 3,
        isCurrentEpisode: false,
      },
      {
        date: "2026-04-01",
        state: "confirmed",
        previousState: "forming",
        reason: "confirmed",
        evidenceMode: "reconstructed",
        methodologyVersion: "squeeze-monitor-v3",
        episodeNumber: 4,
        isCurrentEpisode: false,
      },
      {
        date: "2026-05-01",
        state: "forming",
        previousState: "none",
        reason: "current",
        evidenceMode: "forward",
        methodologyVersion: "squeeze-monitor-v3",
        episodeNumber: 5,
        isCurrentEpisode: true,
      },
    ];

    const labels = buildSqueezeMarkers(path).map((marker) => marker.text);

    expect(labels).toEqual(["C3", "C4", "D5"]);
  });
});
