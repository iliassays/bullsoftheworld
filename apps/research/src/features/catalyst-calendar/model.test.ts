import { describe, expect, it } from "vitest";

import {
  confidenceLabel,
  filterEvents,
  groupByDate,
  timingLabel,
  type CatalystEvent,
} from "./model";

function event(overrides: Partial<CatalystEvent>): CatalystEvent {
  return {
    id: "1",
    code: "GP",
    eventType: "agm",
    title: "GP annual general meeting",
    timingKind: "confirmed",
    confirmedDate: "2026-08-05",
    windowStart: null,
    windowEnd: null,
    status: "scheduled",
    confidence: "official_confirmed",
    sourceType: "dse_announcement",
    sourceRef: "announcement:abc",
    sourceUrl: null,
    knownAt: "2026-07-10T23:59:00Z",
    expectedEvidence: null,
    details: null,
    ...overrides,
  };
}

describe("timingLabel", () => {
  it("shows a confirmed date plainly", () => {
    expect(timingLabel(event({}))).toBe("2026-08-05");
  });

  it("always marks an inferred window as a window, never a date", () => {
    const window = event({
      timingKind: "window",
      confirmedDate: null,
      windowStart: "2026-07-09",
      windowEnd: "2026-08-02",
      confidence: "inferred_cadence",
    });
    expect(timingLabel(window)).toContain("(window)");
    expect(timingLabel(window)).toContain("2026-07-09");
  });
});

describe("groupByDate", () => {
  it("sorts days ascending and confirmed events before windows within a day", () => {
    const groups = groupByDate([
      event({
        id: "w",
        timingKind: "window",
        confirmedDate: null,
        windowStart: "2026-07-20",
        windowEnd: "2026-08-10",
      }),
      event({ id: "later", confirmedDate: "2026-08-01" }),
      event({ id: "c", code: "AAPL", confirmedDate: "2026-07-20" }),
    ]);

    expect(groups.map((group) => group.date)).toEqual(["2026-07-20", "2026-08-01"]);
    expect(groups[0]?.events.map((item) => item.id)).toEqual(["c", "w"]);
  });
});

describe("filterEvents", () => {
  it("filters by ticker substring and event type", () => {
    const events = [event({}), event({ id: "2", code: "AAPL", eventType: "record_date" })];

    expect(filterEvents(events, { code: "aap" })).toHaveLength(1);
    expect(filterEvents(events, { eventType: "record_date" })).toHaveLength(1);
    expect(filterEvents(events, { eventType: "all" })).toHaveLength(2);
  });
});

describe("confidenceLabel", () => {
  it("distinguishes official confirmation from cadence inference", () => {
    expect(confidenceLabel("official_confirmed")).toBe("Official");
    expect(confidenceLabel("inferred_cadence")).toContain("Inferred");
  });
});
