import type {
  SqueezePath,
  SqueezeState,
  SqueezeStateMarker,
} from "../../app/api-client";

const DISPLAYED_STATES = new Set<SqueezeState>([
  "watch",
  "forming",
  "trigger_ready",
  "confirmed",
  "exhausted",
  "failed",
]);

export interface SqueezeLifecycleEvent {
  date: string;
  state: SqueezeState;
  previousState: string | null;
  reason: string;
  close: number | null;
  changeFromDiscoveryPct: number | null;
  changeFromPreviousPct: number | null;
}

function displayedState(marker: SqueezeStateMarker): marker is SqueezeStateMarker & {
  state: SqueezeState;
} {
  return DISPLAYED_STATES.has(marker.state as SqueezeState);
}

function percentageChange(value: number | null, reference: number | null): number | null {
  if (value === null || reference === null || reference <= 0) return null;
  return Number(((value / reference - 1) * 100).toFixed(3));
}

export function buildSqueezeLifecycle(path: SqueezePath): SqueezeLifecycleEvent[] {
  const closeByDate = new Map(path.points.map((point) => [point.date, point.close]));
  const markers = path.stateHistory
    .filter((marker) => marker.isCurrentEpisode)
    .filter(displayedState)
    .sort((left, right) => left.date.localeCompare(right.date));
  const discoveryClose =
    path.entry.discoveryPrice ?? closeByDate.get(path.entry.firstDiscoveredOn) ?? null;
  let previousTransitionClose: number | null = null;

  return markers.map((marker) => {
    const isDiscovery = marker.date === path.entry.firstDiscoveredOn;
    const close = isDiscovery
      ? discoveryClose
      : closeByDate.get(marker.date) ?? null;
    const event: SqueezeLifecycleEvent = {
      date: marker.date,
      state: marker.state,
      previousState: marker.previousState,
      reason: marker.reason,
      close,
      changeFromDiscoveryPct: isDiscovery
        ? null
        : percentageChange(close, discoveryClose),
      changeFromPreviousPct:
        previousTransitionClose === null
          ? null
          : percentageChange(close, previousTransitionClose),
    };
    if (close !== null) previousTransitionClose = close;
    return event;
  });
}
