import type { DossierOverlaySeries, DossierPricePoint } from "./model";

export type WorkbenchLayout = "balanced" | "chart_focus" | "evidence_focus";
export type WorkbenchInspector = "condition" | "evidence" | "fundamentals" | "analyst";
export type WorkbenchOverlayKey =
  | "ema20"
  | "ema50"
  | "levels"
  | "condition"
  | "evidence"
  | "portfolio";

export interface WorkbenchOverlayVisibility {
  ema20: boolean;
  ema50: boolean;
  levels: boolean;
  condition: boolean;
  evidence: boolean;
  portfolio: boolean;
}

export interface WorkbenchPreferences {
  layout: WorkbenchLayout;
  inspector: WorkbenchInspector;
  overlays: WorkbenchOverlayVisibility;
}

export const DEFAULT_WORKBENCH_PREFERENCES: WorkbenchPreferences = {
  layout: "balanced",
  inspector: "condition",
  overlays: {
    ema20: true,
    ema50: true,
    levels: true,
    condition: true,
    evidence: true,
    portfolio: true,
  },
};

const LAYOUTS = new Set<WorkbenchLayout>(["balanced", "chart_focus", "evidence_focus"]);
const INSPECTORS = new Set<WorkbenchInspector>([
  "condition",
  "evidence",
  "fundamentals",
  "analyst",
]);
const OVERLAYS: WorkbenchOverlayKey[] = [
  "ema20",
  "ema50",
  "levels",
  "condition",
  "evidence",
  "portfolio",
];

export function workbenchStorageKey(tenant: string): string {
  return `bulls-atlas:${tenant}:investigation-workbench:v1`;
}

export function parseWorkbenchPreferences(value: string | null): WorkbenchPreferences {
  if (!value) return DEFAULT_WORKBENCH_PREFERENCES;
  try {
    const candidate = JSON.parse(value) as Partial<WorkbenchPreferences>;
    const overlays = { ...DEFAULT_WORKBENCH_PREFERENCES.overlays };
    for (const key of OVERLAYS) {
      if (typeof candidate.overlays?.[key] === "boolean") overlays[key] = candidate.overlays[key];
    }
    return {
      layout: LAYOUTS.has(candidate.layout as WorkbenchLayout)
        ? (candidate.layout as WorkbenchLayout)
        : DEFAULT_WORKBENCH_PREFERENCES.layout,
      inspector: INSPECTORS.has(candidate.inspector as WorkbenchInspector)
        ? (candidate.inspector as WorkbenchInspector)
        : DEFAULT_WORKBENCH_PREFERENCES.inspector,
      overlays,
    };
  } catch {
    return DEFAULT_WORKBENCH_PREFERENCES;
  }
}

function utcWeekKey(date: string): string {
  const value = new Date(`${date}T00:00:00Z`);
  const weekday = value.getUTCDay() || 7;
  value.setUTCDate(value.getUTCDate() - weekday + 1);
  return value.toISOString().slice(0, 10);
}

export function aggregateWeeklyPricePoints(
  points: readonly DossierPricePoint[],
): DossierPricePoint[] {
  const weeks = new Map<string, DossierPricePoint>();
  for (const point of points) {
    const key = utcWeekKey(point.date);
    const current = weeks.get(key);
    if (!current) {
      weeks.set(key, { ...point });
      continue;
    }
    weeks.set(key, {
      date: point.date,
      open: current.open,
      high: Math.max(current.high, point.high),
      low: Math.min(current.low, point.low),
      close: point.close,
      volume: current.volume + point.volume,
      benchmarkClose: point.benchmarkClose,
    });
  }
  return [...weeks.values()];
}

export function aggregateWeeklyOverlays(
  overlays: readonly DossierOverlaySeries[],
): DossierOverlaySeries[] {
  return overlays.map((overlay) => {
    const weeks = new Map<string, { date: string; value: number }>();
    for (const point of overlay.points) weeks.set(utcWeekKey(point.date), { ...point });
    return { ...overlay, points: [...weeks.values()] };
  });
}

export function weeklyDisplayDateMap(
  points: readonly DossierPricePoint[],
): ReadonlyMap<string, string> {
  const lastSessionByWeek = new Map<string, string>();
  for (const point of points) lastSessionByWeek.set(utcWeekKey(point.date), point.date);
  return new Map(points.map((point) => [point.date, lastSessionByWeek.get(utcWeekKey(point.date))!]));
}

export function updateOverlayVisibility(
  visibility: WorkbenchOverlayVisibility,
  key: WorkbenchOverlayKey,
): WorkbenchOverlayVisibility {
  return { ...visibility, [key]: !visibility[key] };
}
