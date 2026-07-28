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

type DisplayedMarker = SqueezeStateMarker & { state: SqueezeState };

export interface SqueezeLifecycleEvent {
  date: string;
  state: SqueezeState;
  previousState: string | null;
  reason: string;
  close: number | null;
  changeFromDiscoveryPct: number | null;
  changeFromPreviousPct: number | null;
  episodeNumber: number;
  isCurrentEpisode: boolean;
  evidenceMode: "forward" | "reconstructed";
  methodologyVersion: string;
  isEpisodeStart: boolean;
}

export interface SqueezeLifecycleEpisode {
  episodeNumber: number;
  isCurrentEpisode: boolean;
  startedOn: string;
  endedOn: string;
  evidenceMode: "forward" | "reconstructed";
  methodologyVersions: string[];
  events: SqueezeLifecycleEvent[];
}

function displayedState(marker: SqueezeStateMarker): marker is DisplayedMarker {
  return DISPLAYED_STATES.has(marker.state as SqueezeState);
}

function percentageChange(value: number | null, reference: number | null): number | null {
  if (value === null || reference === null || reference <= 0) return null;
  return Number(((value / reference - 1) * 100).toFixed(3));
}

export function buildSqueezeLifecycle(path: SqueezePath): SqueezeLifecycleEvent[] {
  return (
    buildSqueezeLifecycleEpisodes(path).find((episode) => episode.isCurrentEpisode)
      ?.events ?? []
  );
}

export function buildSqueezeLifecycleEpisodes(
  path: SqueezePath,
): SqueezeLifecycleEpisode[] {
  const closeByDate = new Map(path.points.map((point) => [point.date, point.close]));
  const markers = path.stateHistory
    .filter(displayedState)
    .sort(
      (left, right) =>
        left.episodeNumber - right.episodeNumber || left.date.localeCompare(right.date),
    );
  const grouped = new Map<number, DisplayedMarker[]>();

  for (const marker of markers) {
    const episode = grouped.get(marker.episodeNumber) ?? [];
    episode.push(marker);
    grouped.set(marker.episodeNumber, episode);
  }

  return [...grouped.entries()].map(([episodeNumber, episodeMarkers]) => {
    const isCurrentEpisode = episodeMarkers.some((marker) => marker.isCurrentEpisode);
    let baselineClose: number | null = null;
    let previousTransitionClose: number | null = null;
    const events = episodeMarkers.map((marker, index) => {
      const isCurrentDiscovery =
        isCurrentEpisode && marker.date === path.entry.firstDiscoveredOn;
      const close = isCurrentDiscovery
        ? path.entry.discoveryPrice ?? closeByDate.get(marker.date) ?? null
        : closeByDate.get(marker.date) ?? null;
      if (index === 0) baselineClose = close;
      const event: SqueezeLifecycleEvent = {
        date: marker.date,
        state: marker.state,
        previousState: marker.previousState,
        reason: marker.reason,
        close,
        changeFromDiscoveryPct:
          index === 0 ? null : percentageChange(close, baselineClose),
        changeFromPreviousPct:
          previousTransitionClose === null
            ? null
            : percentageChange(close, previousTransitionClose),
        episodeNumber,
        isCurrentEpisode,
        evidenceMode: marker.evidenceMode,
        methodologyVersion: marker.methodologyVersion,
        isEpisodeStart: index === 0,
      };
      if (close !== null) previousTransitionClose = close;
      return event;
    });
    const methodologyVersions = [
      ...new Set(episodeMarkers.map((marker) => marker.methodologyVersion)),
    ];

    return {
      episodeNumber,
      isCurrentEpisode,
      startedOn: events[0]!.date,
      endedOn: events.at(-1)!.date,
      evidenceMode: episodeMarkers.some(
        (marker) => marker.evidenceMode === "reconstructed",
      )
        ? "reconstructed"
        : "forward",
      methodologyVersions,
      events,
    };
  });
}
