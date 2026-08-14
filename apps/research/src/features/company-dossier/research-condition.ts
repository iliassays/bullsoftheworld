import type {
  ResearchConditionEvaluation,
  ResearchConditionKey,
  ResearchConditionWorkbench,
} from "./model";

export type DossierChartMode = "price" | "relative";
export type DossierChartRange = "3M" | "6M" | "1Y";
export type DossierChartTimeframe = "1D" | "1W";

const CHART_MODES = new Set<DossierChartMode>(["price", "relative"]);
const CHART_RANGES = new Set<DossierChartRange>(["3M", "6M", "1Y"]);
const CHART_TIMEFRAMES = new Set<DossierChartTimeframe>(["1D", "1W"]);

export function chartMode(value: string | null): DossierChartMode {
  return CHART_MODES.has(value as DossierChartMode) ? (value as DossierChartMode) : "price";
}

export function chartRange(value: string | null): DossierChartRange {
  return CHART_RANGES.has(value as DossierChartRange)
    ? (value as DossierChartRange)
    : "1Y";
}

export function chartTimeframe(value: string | null): DossierChartTimeframe {
  return CHART_TIMEFRAMES.has(value as DossierChartTimeframe)
    ? (value as DossierChartTimeframe)
    : "1D";
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
