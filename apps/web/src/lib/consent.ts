export const ANALYTICS_CONSENT_KEY = "bulls.euConsent.v1";
export const ANALYTICS_CONSENT_EVENT = "bulls:analytics-consent";
export const ANALYTICS_CONSENT_OPEN_EVENT = "bulls:analytics-consent-open";

export function looksEuropean(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone?.startsWith("Europe/") ?? false;
  } catch {
    return false;
  }
}

export function storedAnalyticsConsent(): "granted" | "denied" | null {
  if (typeof window === "undefined") return null;
  const value = localStorage.getItem(ANALYTICS_CONSENT_KEY);
  return value === "granted" || value === "denied" ? value : null;
}

export function analyticsAllowed(): boolean {
  if (!looksEuropean()) return true;
  return storedAnalyticsConsent() === "granted";
}

export function applyAnalyticsConsent(granted: boolean): void {
  const value = granted ? "granted" : "denied";
  localStorage.setItem(ANALYTICS_CONSENT_KEY, value);
  const w = window as typeof window & { gtag?: (...args: unknown[]) => void };
  w.gtag?.("consent", "update", {
    ad_storage: value,
    analytics_storage: value,
    ad_user_data: value,
    ad_personalization: value,
  });
  window.dispatchEvent(new CustomEvent(ANALYTICS_CONSENT_EVENT, { detail: value }));
}

export function openAnalyticsConsent(): void {
  window.dispatchEvent(new Event(ANALYTICS_CONSENT_OPEN_EVENT));
}
