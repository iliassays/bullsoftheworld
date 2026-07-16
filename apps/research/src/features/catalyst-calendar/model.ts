export type CatalystTimingKind = "confirmed" | "window";
export type CatalystConfidence = "official_confirmed" | "official_derived" | "inferred_cadence";
export type CatalystStatus = "scheduled" | "occurred" | "cancelled";

export interface CatalystEvent {
  id: string;
  code: string;
  eventType: string;
  title: string;
  timingKind: CatalystTimingKind;
  confirmedDate: string | null;
  windowStart: string | null;
  windowEnd: string | null;
  status: CatalystStatus;
  confidence: CatalystConfidence;
  sourceType: string;
  sourceRef: string;
  sourceUrl: string | null;
  knownAt: string;
  expectedEvidence: string | null;
  details: Record<string, unknown> | null;
}

export interface CatalystCalendar {
  tenantId: string;
  market: string;
  workspaceId: string;
  generatedAt: string;
  horizonDays: number;
  events: CatalystEvent[];
}

export const HORIZON_OPTIONS = [14, 30, 60, 90] as const;
export type HorizonDays = (typeof HORIZON_OPTIONS)[number];

const EVENT_TYPE_LABELS: Record<string, string> = {
  record_date: "Record date",
  agm: "AGM",
  egm: "EGM",
  board_meeting: "Board meeting",
  spot_window: "Spot window",
  periodic_report_window: "Expected report",
};

export function eventTypeLabel(eventType: string): string {
  return EVENT_TYPE_LABELS[eventType] ?? eventType.split("_").join(" ");
}

/** The honest timing sentence: an inferred window must never read like a confirmed date. */
export function timingLabel(event: CatalystEvent): string {
  if (event.timingKind === "confirmed" && event.confirmedDate) {
    return event.confirmedDate;
  }
  return `${event.windowStart ?? "?"} → ${event.windowEnd ?? "?"} (window)`;
}

export function confidenceLabel(confidence: CatalystConfidence): string {
  switch (confidence) {
    case "official_confirmed":
      return "Official";
    case "official_derived":
      return "Official (derived)";
    case "inferred_cadence":
      return "Inferred from filing cadence";
  }
}

export function anchorDate(event: CatalystEvent): string {
  return event.confirmedDate ?? event.windowStart ?? "";
}

export interface CalendarDayGroup {
  date: string;
  events: CatalystEvent[];
}

/** Group by anchor date ascending; within a day, confirmed events sort before windows. */
export function groupByDate(events: CatalystEvent[]): CalendarDayGroup[] {
  const byDate = new Map<string, CatalystEvent[]>();
  for (const event of events) {
    const date = anchorDate(event);
    if (!date) continue;
    const bucket = byDate.get(date) ?? [];
    bucket.push(event);
    byDate.set(date, bucket);
  }
  return [...byDate.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, dayEvents]) => ({
      date,
      events: [...dayEvents].sort((a, b) => {
        if (a.timingKind !== b.timingKind) return a.timingKind === "confirmed" ? -1 : 1;
        return a.code.localeCompare(b.code);
      }),
    }));
}

export function filterEvents(
  events: CatalystEvent[],
  filters: { code?: string; eventType?: string },
): CatalystEvent[] {
  const code = filters.code?.trim().toUpperCase();
  return events.filter((event) => {
    if (code && !event.code.toUpperCase().includes(code)) return false;
    if (filters.eventType && filters.eventType !== "all" && event.eventType !== filters.eventType) {
      return false;
    }
    return true;
  });
}
