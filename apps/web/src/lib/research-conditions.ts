import type { PublicConditionKey } from "./api";

const CONDITION_KEYS = new Set<PublicConditionKey>([
  "trend_alignment",
  "participation_expansion",
  "controlled_pullback_context",
]);

export function researchConditionFromSearch(value: string | null): PublicConditionKey | null {
  return value && CONDITION_KEYS.has(value as PublicConditionKey)
    ? (value as PublicConditionKey)
    : null;
}

export function buildAtlasConditionUrl(
  researchSiteUrl: string,
  condition: PublicConditionKey,
  size?: string,
): string {
  const url = new URL("/conditions", researchSiteUrl);
  url.searchParams.set("condition", condition);
  if (size) url.searchParams.set("cap", size);
  return url.toString();
}

export function hasLaterConditionClose(observedOn: string, latestSessionDate: string): boolean {
  return latestSessionDate > observedOn;
}
