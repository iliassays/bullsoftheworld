import { describe, expect, it } from "vitest";

import { atlasSessionId, buildAtlasEventPayload } from "./analytics";
import { writeAnalyticsConsent, type AtlasExperienceIdentity } from "./model";

class MemoryStorage {
  private readonly values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

const identity: AtlasExperienceIdentity = { tenant: "bullsofwallst", userId: 7 };

describe("Atlas product analytics", () => {
  it("fails closed until the account explicitly grants consent", () => {
    const local = new MemoryStorage();
    const session = new MemoryStorage();

    expect(
      buildAtlasEventPayload(
        identity,
        "atlas_route_view",
        "/companies/NXTC",
        { atlas_stage: "investigate" },
        local,
        session,
        () => "session-1",
      ),
    ).toBeNull();

    writeAnalyticsConsent(identity, "denied", local);
    expect(
      buildAtlasEventPayload(
        identity,
        "atlas_route_view",
        "/companies/NXTC",
        {},
        local,
        session,
      ),
    ).toBeNull();
  });

  it("removes ticker and query data from consented events", () => {
    const local = new MemoryStorage();
    const session = new MemoryStorage();
    writeAnalyticsConsent(identity, "granted", local);

    const payload = buildAtlasEventPayload(
      identity,
      "atlas_route_view",
      "/companies/NXTC?tab=filings",
      { atlas_stage: "investigate", destination: "/companies/:ticker" },
      local,
      session,
      () => "session-1",
    );

    expect(payload).toMatchObject({
      analytics_consent: true,
      name: "atlas_route_view",
      path: "/companies/:ticker",
      session_id: "session-1",
      properties: {
        atlas_stage: "investigate",
        market: "US",
        surface: "atlas",
      },
    });
    expect(JSON.stringify(payload)).not.toContain("NXTC");
    expect(JSON.stringify(payload)).not.toContain("filings");
  });

  it("reuses a tenant-scoped pseudonymous session identifier", () => {
    const session = new MemoryStorage();
    expect(atlasSessionId(identity, session, () => "first")).toBe("first");
    expect(atlasSessionId(identity, session, () => "second")).toBe("first");

    const dseIdentity: AtlasExperienceIdentity = { tenant: "bullsofdhaka", userId: 7 };
    expect(atlasSessionId(dseIdentity, session, () => "dse-session")).toBe("dse-session");

    const secondUser: AtlasExperienceIdentity = { tenant: "bullsofwallst", userId: 8 };
    expect(atlasSessionId(secondUser, session, () => "second-user")).toBe("second-user");
  });
});
