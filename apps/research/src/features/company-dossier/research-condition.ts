import type {
  ResearchConditionEvaluation,
  ResearchConditionKey,
  ResearchConditionWorkbench,
} from "./model";

export type DossierChartMode = "price" | "relative";
export type DossierChartRange = "3M" | "6M" | "1Y";

const CHART_MODES = new Set<DossierChartMode>(["price", "relative"]);
const CHART_RANGES = new Set<DossierChartRange>(["3M", "6M", "1Y"]);

export function chartMode(value: string | null): DossierChartMode {
  return CHART_MODES.has(value as DossierChartMode) ? (value as DossierChartMode) : "price";
}

export function chartRange(value: string | null): DossierChartRange {
  return CHART_RANGES.has(value as DossierChartRange)
    ? (value as DossierChartRange)
    : "1Y";
}

export function selectedCondition(
  workbench: ResearchConditionWorkbench,
  requested: string | null,
): ResearchConditionEvaluation {
  const requestedMatch = workbench.conditions.find((item) => item.key === requested);
  return requestedMatch
    ?? workbench.conditions.find((item) => item.state === "observed")
    ?? workbench.conditions.find((item) => item.state !== "unavailable")
    ?? workbench.conditions[0]!;
}

export function conditionUrlKey(condition: ResearchConditionEvaluation): ResearchConditionKey {
  return condition.key;
}

export function formatObservedValue(
  value: number | null,
  unit: "percent" | "multiple",
): string {
  if (value === null) return "Not available";
  if (unit === "multiple") return `${value.toFixed(2)}x`;
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}
