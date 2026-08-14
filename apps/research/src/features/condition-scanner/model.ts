export type ConditionKey =
  | "trend_alignment"
  | "participation_expansion"
  | "controlled_pullback_context";

export type ConditionEvidenceMode = "forward" | "reconstructed";

const CONDITION_KEYS = new Set<ConditionKey>([
  "trend_alignment",
  "participation_expansion",
  "controlled_pullback_context",
]);

export function conditionKeyFromSearch(value: string | null): ConditionKey {
  return value && CONDITION_KEYS.has(value as ConditionKey)
    ? (value as ConditionKey)
    : "trend_alignment";
}

export function capTierFromSearch(value: string | null, allowed: readonly string[]): string {
  return value && allowed.includes(value) ? value : "all";
}

export function observationFilterFromSearch(value: string | null): "all" | "new" {
  return value === "new" ? "new" : "all";
}

export interface ConditionDefinition {
  key: ConditionKey;
  version: string;
  title: string;
  category: string;
  whyItMatters: string;
  limitation: string;
}

export interface ConditionCheck {
  factKey: string;
  label: string;
  observed: number | null;
  expected: string;
  unit: "percent" | "multiple";
  passed: boolean | null;
}

export interface ConditionCalibration {
  conditionKey: ConditionKey;
  conditionVersion: string;
  evidenceMode: ConditionEvidenceMode;
  horizonSessions: 1 | 5 | 20 | 60;
  asOfDate: string;
  historyStartDate: string | null;
  observations: number;
  matured: number;
  pending: number;
  medianReturnPct: number | null;
  positiveRatePct: number | null;
  medianExcessReturnPct: number | null;
  benchmarkObservations: number;
  averageMaxFavorablePct: number | null;
  averageMaxAdversePct: number | null;
  universeSize: number;
  pointInTimeComplete: boolean;
  warningText: string | null;
}

export interface ConditionScanItem {
  ticker: string;
  company: string;
  sector: string | null;
  capTier: string;
  observedOn: string;
  latestSessionDate: string;
  referenceClose: number;
  latestClose: number;
  closeReturnSinceObservationPct: number;
  averageDailyValueMn: number | null;
  evidenceMode: ConditionEvidenceMode;
  isNew: boolean;
  subscribed: boolean;
  checks: ConditionCheck[];
}

export interface ConditionScan {
  tenantId: string;
  market: "DSE" | "US";
  workspaceId: string;
  generatedAt: string;
  latestSessionDate: string | null;
  methodologyVersion: string;
  definition: ConditionDefinition;
  observedCount: number;
  newCount: number;
  returnedCount: number;
  items: ConditionScanItem[];
  calibrations: ConditionCalibration[];
  warnings: string[];
}

export interface ConditionSubscription {
  tenantId: string;
  market: "DSE" | "US";
  ticker: string;
  conditionKey: ConditionKey;
  conditionVersion: string;
  methodologyVersion: string;
  enabled: boolean;
  lastAlertedOn: string | null;
}

export function calibrationFor(
  calibrations: ConditionCalibration[],
  mode: ConditionEvidenceMode,
  horizon: number,
): ConditionCalibration | undefined {
  return calibrations.find(
    (calibration) =>
      calibration.evidenceMode === mode && calibration.horizonSessions === horizon,
  );
}

export function formatConditionValue(check: ConditionCheck): string {
  if (check.observed === null) return "Unavailable";
  if (check.unit === "multiple") return `${check.observed.toFixed(2)}x`;
  return `${check.observed >= 0 ? "+" : ""}${check.observed.toFixed(2)}%`;
}

export function signedPercent(value: number | null): string {
  if (value === null) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}
