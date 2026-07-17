import { describe, expect, it } from "vitest";

import { buildPortalTickerUrl } from "./deployment";

describe("buildPortalTickerUrl", () => {
  it("builds the canonical DSE public ticker route", () => {
    expect(buildPortalTickerUrl("https://bullsofdhaka.com", "en", " bxpharma ")).toBe(
      "https://bullsofdhaka.com/en/s/BXPHARMA",
    );
  });

  it("preserves supported class-share punctuation on the US route", () => {
    expect(buildPortalTickerUrl("https://bullsofwallst.com", "en", "brk.b")).toBe(
      "https://bullsofwallst.com/en/s/BRK.B",
    );
  });

  it("rejects an empty ticker", () => {
    expect(() => buildPortalTickerUrl("https://bullsofdhaka.com", "en", "  ")).toThrow(
      "A ticker is required",
    );
  });
});
