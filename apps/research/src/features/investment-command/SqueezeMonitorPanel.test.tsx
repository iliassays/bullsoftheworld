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

    expect(html).toContain("First confirmed");
    expect(html).toContain("Next observable open");
    expect(html).toContain("Gross follow-through");
    expect(html).toContain("after confirmation · not P&amp;L");
    expect(html).toContain("pre-confirmation move included");
    expect(html).toContain("Archive method squeeze-monitor-v3");
  });
});
