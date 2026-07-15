export const ALL_UNIVERSE = "all" as const;

export type UniverseTier =
  | typeof ALL_UNIVERSE
  | "mega"
  | "large"
  | "mid"
  | "small"
  | "micro";

export function normalizeUniverseTier(
  value: string | null | undefined,
  available: readonly string[],
): UniverseTier {
  if (value && available.includes(value)) return value as UniverseTier;
  return ALL_UNIVERSE;
}

export function universeStorageKey(tenant: string): string {
  return `bulls.universe.${tenant}`;
}
