import { describe, expect, it } from "vitest";

import { managerGuideForPath } from "./manager-guides";

describe("managerGuideForPath", () => {
  it.each([
    ["/today", "Today"],
    ["/portfolio", "Portfolio & risk"],
    ["/hypotheses", "Strategy lab"],
    ["/queue", "Research inbox"],
    ["/companies/GP", "Company research"],
    ["/catalysts", "Catalysts"],
    ["/operations", "Automation & audit"],
    ["/memory", "Research memory"],
  ])("maps %s to its manager guide", (path, section) => {
    expect(managerGuideForPath(path).section).toBe(section);
  });

  it("keeps the operating clocks explicit", () => {
    const guide = managerGuideForPath("/operations");
    expect(guide.question).toContain("research process");
  });
});
