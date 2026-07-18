import { describe, expect, it } from "vitest";

import { strategySelectionGuide } from "./strategy-guide";

describe("strategySelectionGuide", () => {
  it("explains that DSE paper selection is independent from queue urgency", () => {
    const guide = strategySelectionGuide("dse_reversal_v1", 25);

    expect(guide.universe).toContain("25 active liquid securities");
    expect(guide.entry).toContain("12% below");
    expect(guide.entry).toContain("BDT 2m");
    expect(guide.ranking).toContain("queue urgency is not used");
  });

  it("returns the registered US trend gates", () => {
    const guide = strategySelectionGuide("us_breakout_v1", 30);

    expect(guide.universe).toContain("30 active liquid securities");
    expect(guide.entry).toContain("50-day above 200-day");
    expect(guide.sizing).toContain("10% position cap");
  });
});
