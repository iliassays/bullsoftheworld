export type AnalyticsConsent = "unknown" | "granted" | "denied";

const CONSENT_KEY = "bulls.consent.v1";
const CONSENT_VERSION = 1;

interface StoredConsent {
  version: number;
  analytics: Exclude<AnalyticsConsent, "unknown">;
  updated_at: string;
}

export function readAnalyticsConsent(): AnalyticsConsent {
  if (typeof window === "undefined") return "unknown";
  try {
    const parsed = JSON.parse(localStorage.getItem(CONSENT_KEY) ?? "null") as StoredConsent | null;
    if (
      parsed?.version === CONSENT_VERSION &&
      (parsed.analytics === "granted" || parsed.analytics === "denied")
    ) {
      return parsed.analytics;
    }
  } catch {
    // A blocked or corrupted store is treated as no consent.
  }
  return "unknown";
}

export function writeAnalyticsConsent(value: Exclude<AnalyticsConsent, "unknown">) {
  const record: StoredConsent = {
    version: CONSENT_VERSION,
    analytics: value,
    updated_at: new Date().toISOString(),
  };
  try {
    localStorage.setItem(CONSENT_KEY, JSON.stringify(record));
  } catch {
    // The in-memory choice still applies for this page when storage is unavailable.
  }
}

export function analyticsConsentGranted(): boolean {
  return readAnalyticsConsent() === "granted";
}
