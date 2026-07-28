import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const queryMock = vi.hoisted(() => vi.fn());

vi.mock("@tanstack/react-query", () => ({
  useQuery: queryMock,
}));

import { SqueezeMonitorPanel } from "./SqueezeMonitorPanel";
import { previewSqueezeMonitor, previewSqueezePath } from "./preview-data";

function pathQuery() {
  return {
    data: undefined,
    error: null,
    isError: false,
    isLoading: false,
    refetch: vi.fn(),
  };
}

describe("SqueezeMonitorPanel availability states", () => {
  beforeEach(() => {
    queryMock.mockReset();
  });

  it("keeps the panel visible while the archive is loading", () => {
    queryMock.mockImplementation(({ queryKey }: { queryKey: string[] }) =>
      queryKey[1] === "squeeze-monitor"
        ? {
            data: undefined,
            error: null,
            isError: false,
            isLoading: true,
            refetch: vi.fn(),
          }
        : pathQuery(),
    );

    const html = renderToStaticMarkup(<SqueezeMonitorPanel />);

    expect(html).toContain("Squeeze monitor");
    expect(html).toContain("Loading archive");
    expect(html).toContain("Loading squeeze monitor");
  });

  it("shows a retryable error instead of removing the panel", () => {
    queryMock.mockImplementation(({ queryKey }: { queryKey: string[] }) =>
      queryKey[1] === "squeeze-monitor"
        ? {
            data: undefined,
            error: new Error("archive request failed"),
            isError: true,
            isLoading: false,
            refetch: vi.fn(),
          }
        : pathQuery(),
    );

    const html = renderToStaticMarkup(<SqueezeMonitorPanel />);

    expect(html).toContain("Squeeze monitor unavailable");
    expect(html).toContain("archive request failed");
    expect(html).toContain("Retry");
  });

  it("separates discovery follow-through from the next observable session", () => {
    queryMock.mockImplementation(({ queryKey }: { queryKey: string[] }) =>
      queryKey[1] === "squeeze-monitor"
        ? {
            data: previewSqueezeMonitor,
            error: null,
            isError: false,
            isLoading: false,
            refetch: vi.fn(),
          }
        : {
            ...pathQuery(),
            data: previewSqueezePath(
              previewSqueezeMonitor.families[0]!.entries[0]!.family,
              previewSqueezeMonitor.families[0]!.entries[0]!.code,
            ),
          },
    );

    const html = renderToStaticMarkup(<SqueezeMonitorPanel />);

    expect(html).toContain("New today");
    expect(html).toContain("Research scan only. No order is created from this list.");
    expect(html).toContain("not high probability");
    expect(html).toMatch(/Confirmed today|New setup/);
    expect(html).toContain("First confirmed");
    expect(html).toContain("before confirmation");
    expect(html).toContain("Next observable open");
    expect(html).toContain("Gross follow-through");
    expect(html).toContain("after confirmation · not P&amp;L");
    expect(html).toContain("pre-confirmation move included");
    expect(html).toContain("Archive method squeeze-monitor-v3");
    expect(html).toContain("Pre-confirmation");
    expect(html).toContain("Setup journey");
    expect(html).toContain("Current episode");
    expect(html).toContain("Episode baseline");
    expect(html).toContain("from episode start");
    expect(html).toContain("Earlier episodes");
    expect(html).toContain("Historical replay");
    expect(html).toContain("archived snapshot for");
  });

  it("groups watch, forming and trigger-ready as pre-confirmation states", () => {
    const entry = previewSqueezeMonitor.families[0]!.entries[0]!;
    const monitorWithWatch = {
      ...previewSqueezeMonitor,
      families: [
        {
          ...previewSqueezeMonitor.families[0]!,
          entries: [{ ...entry, state: "watch" as const, isNew: false }],
        },
      ],
    };
    queryMock.mockImplementation(({ queryKey }: { queryKey: string[] }) =>
      queryKey[1] === "squeeze-monitor"
        ? {
            data: monitorWithWatch,
            error: null,
            isError: false,
            isLoading: false,
            refetch: vi.fn(),
          }
        : pathQuery(),
    );

    const html = renderToStaticMarkup(<SqueezeMonitorPanel />);

    expect(html).toMatch(/Pre-confirmation[\s\S]*?1/);
  });

  it("explains a direct legacy confirmation without inventing prior phases", () => {
    const sourceEntry = previewSqueezeMonitor.families[0]!.entries[0]!;
    const directEntry = {
      ...sourceEntry,
      firstDiscoveredOn: sourceEntry.asOfDate,
      firstConfirmedOn: sourceEntry.asOfDate,
      discoveryPrice: sourceEntry.asOfPrice,
      confirmationPrice: sourceEntry.asOfPrice,
      moveToConfirmationPct: 0,
      methodologyVersion: "squeeze-monitor-v1",
    };
    const directMonitor = {
      ...previewSqueezeMonitor,
      families: previewSqueezeMonitor.families.map((family, familyIndex) => ({
        ...family,
        entries: familyIndex === 0 ? [directEntry] : family.entries,
      })),
    };
    const directPath = previewSqueezePath(directEntry.family, directEntry.code);
    directPath.entry = directEntry;
    directPath.stateHistory = [
      ...directPath.stateHistory.filter((marker) => !marker.isCurrentEpisode),
      {
        date: directEntry.asOfDate,
        state: "confirmed",
        previousState: "none",
        reason: "The first retained observation met the legacy confirmation rule.",
        evidenceMode: "forward",
        methodologyVersion: "squeeze-monitor-v1",
        episodeNumber: directPath.discoveryNumber,
        isCurrentEpisode: true,
      },
    ];
    queryMock.mockImplementation(({ queryKey }: { queryKey: string[] }) =>
      queryKey[1] === "squeeze-monitor"
        ? {
            data: directMonitor,
            error: null,
            isError: false,
            isLoading: false,
            refetch: vi.fn(),
          }
        : {
            ...pathQuery(),
            data: directPath,
          },
    );

    const html = renderToStaticMarkup(<SqueezeMonitorPanel />);

    expect(html).toContain("Legacy archived classification");
    expect(html).toContain("Confirmed at first observation");
    expect(html).toContain("missing phases are not inferred");
    expect(html).toContain("Legacy methodology boundary");
    expect(html).toContain("same-session classification; no earlier phase recorded");
    expect(html).not.toContain("+0.00% before confirmation");
  });

  it("renders a same-session discovery as pending rather than positive zero", () => {
    const pendingMonitor = {
      ...previewSqueezeMonitor,
      families: previewSqueezeMonitor.families.map((family, familyIndex) => ({
        ...family,
        entries:
          familyIndex === 0
            ? family.entries.map((entry, entryIndex) =>
                entryIndex === 0
                  ? {
                      ...entry,
                      sessionsSinceDiscovery: 0,
                      returnSinceDiscoveryPct: null,
                      maxFavorablePct: null,
                      maxAdversePct: null,
                      peakTradedPct: null,
                      troughTradedPct: null,
                    }
                  : entry,
              )
            : family.entries,
      })),
    };
    queryMock.mockImplementation(({ queryKey }: { queryKey: string[] }) =>
      queryKey[1] === "squeeze-monitor"
        ? {
            data: pendingMonitor,
            error: null,
            isError: false,
            isLoading: false,
            refetch: vi.fn(),
          }
        : pathQuery(),
    );

    const html = renderToStaticMarkup(<SqueezeMonitorPanel />);

    expect(html).toContain("Pending");
    expect(html).toContain("awaiting next close");
    expect(html).toContain("0 sessions");
  });
});
