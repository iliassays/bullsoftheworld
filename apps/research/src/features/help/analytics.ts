import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import {
  researchApi,
  type AtlasProductEventName,
  type AtlasProductEventProperties,
} from "../../app/api-client";
import {
  ATLAS_EXPERIENCE_VERSION,
  elapsedBucket,
  experienceStorageKeys,
  readAnalyticsConsent,
  sanitizeAtlasPath,
  workflowStageForPath,
  type AtlasExperienceIdentity,
} from "./model";

export const ATLAS_CONSENT_CHANGED_EVENT = "bulls:atlas-analytics-consent";

interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

interface AtlasEventPayload {
  analytics_consent: true;
  name: AtlasProductEventName;
  path: string;
  properties: AtlasProductEventProperties;
  session_id: string;
}

function createSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export function atlasSessionId(
  identity: AtlasExperienceIdentity,
  storage: StorageLike,
  idFactory: () => string = createSessionId,
): string {
  const key = experienceStorageKeys(identity).session;
  const existing = storage.getItem(key);
  if (existing) return existing;
  const created = idFactory().slice(0, 64);
  storage.setItem(key, created);
  return created;
}

export function buildAtlasEventPayload(
  identity: AtlasExperienceIdentity,
  name: AtlasProductEventName,
  pathname: string,
  properties: AtlasProductEventProperties,
  localStorage: StorageLike,
  sessionStorage: StorageLike,
  idFactory?: () => string,
): AtlasEventPayload | null {
  if (readAnalyticsConsent(identity, localStorage) !== "granted") return null;
  return {
    analytics_consent: true,
    name,
    path: sanitizeAtlasPath(pathname),
    properties: {
      atlas_version: ATLAS_EXPERIENCE_VERSION,
      market: identity.tenant === "bullsofdhaka" ? "DSE" : "US",
      surface: "atlas",
      ...properties,
    },
    session_id: atlasSessionId(identity, sessionStorage, idFactory),
  };
}

export async function trackAtlasEvent(
  identity: AtlasExperienceIdentity,
  name: AtlasProductEventName,
  pathname: string,
  properties: AtlasProductEventProperties = {},
): Promise<void> {
  if (typeof window === "undefined") return;
  try {
    const payload = buildAtlasEventPayload(
      identity,
      name,
      pathname,
      properties,
      window.localStorage,
      window.sessionStorage,
    );
    if (!payload) return;
    await researchApi.productEvent(payload);
  } catch {
    // Product analytics must never interrupt a research workflow.
  }
}

export function notifyAtlasConsentChanged(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(ATLAS_CONSENT_CHANGED_EVENT));
}

export function useAtlasRouteAnalytics(identity: AtlasExperienceIdentity): void {
  const location = useLocation();
  const sessionStartedAt = useRef(Date.now());
  const previousPath = useRef<string | null>(null);
  const [consentRevision, setConsentRevision] = useState(0);

  useEffect(() => {
    const refresh = () => setConsentRevision((value) => value + 1);
    window.addEventListener(ATLAS_CONSENT_CHANGED_EVENT, refresh);
    return () => window.removeEventListener(ATLAS_CONSENT_CHANGED_EVENT, refresh);
  }, []);

  useEffect(() => {
    const path = sanitizeAtlasPath(location.pathname);
    const stage = workflowStageForPath(path);
    const entryPoint = previousPath.current
      ? workflowStageForPath(previousPath.current) ?? "other"
      : "session_start";

    void trackAtlasEvent(identity, "atlas_route_view", path, {
      atlas_stage: stage ?? "other",
      destination: path,
      entry_point: entryPoint,
      route_group: stage ?? "other",
    });

    if (stage) {
      void trackAtlasEvent(identity, "atlas_workflow_stage_opened", path, {
        atlas_stage: stage,
        entry_point: entryPoint,
        route_group: stage,
      });
    }

    if (path === "/portfolio" && previousPath.current !== "/portfolio") {
      void trackAtlasEvent(identity, "atlas_decision_surface_reached", path, {
        atlas_stage: "allocate",
        elapsed_bucket: elapsedBucket(Date.now() - sessionStartedAt.current),
        entry_point: entryPoint,
      });
    }
    previousPath.current = path;
  }, [consentRevision, identity, location.pathname]);
}
