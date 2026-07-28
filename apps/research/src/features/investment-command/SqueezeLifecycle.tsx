import {
  ChevronRight,
  History,
  Milestone,
  ShieldAlert,
} from "lucide-react";

import type { SqueezePath } from "../../app/api-client";
import { StatusBadge } from "../../design-system";
import {
  buildSqueezeLifecycleEpisodes,
  type SqueezeLifecycleEpisode,
  type SqueezeLifecycleEvent,
} from "./squeeze-lifecycle";
import {
  SQUEEZE_STATE_LABEL,
  SQUEEZE_STATE_TONE,
  squeezeStateLabel,
} from "./squeeze-state";

function signed(value: number | null): string {
  if (value === null) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function closePrice(value: number | null, currency: string): string {
  if (value === null) return "Close unavailable";
  return `${currency} ${value.toLocaleString("en-US", {
    maximumFractionDigits: value < 10 ? 3 : 2,
    minimumFractionDigits: 2,
  })}`;
}

function isDirectConfirmation(event: SqueezeLifecycleEvent): boolean {
  return (
    event.isEpisodeStart &&
    event.state === "confirmed" &&
    (event.previousState === null || event.previousState === "none")
  );
}

function evidenceLabel(episode: SqueezeLifecycleEpisode): string {
  return episode.evidenceMode === "reconstructed"
    ? "Historical replay"
    : "Forward record";
}

function methodologyLabel(episode: SqueezeLifecycleEpisode): string {
  return episode.methodologyVersions.join(" → ");
}

function EventButton({
  code,
  currency,
  event,
  onSelectDate,
  selectedDate,
}: {
  code: string;
  currency: string;
  event: SqueezeLifecycleEvent;
  onSelectDate: (date: string) => void;
  selectedDate: string;
}) {
  const current = event.date === selectedDate;
  const directConfirmation = isDirectConfirmation(event);

  return (
    <button
      aria-current={current ? "date" : undefined}
      aria-label={`Open ${event.date} archived snapshot for ${code}`}
      onClick={() => onSelectDate(event.date)}
      title={`Open the ${event.date} archived snapshot`}
      type="button"
    >
      <span className="squeeze-lifecycle__event-heading">
        <StatusBadge tone={SQUEEZE_STATE_TONE[event.state]}>
          {SQUEEZE_STATE_LABEL[event.state]}
        </StatusBadge>
        <time dateTime={event.date}>{event.date}</time>
        <ChevronRight aria-hidden="true" size={13} />
      </span>
      <strong>{closePrice(event.close, currency)}</strong>
      <span className="squeeze-lifecycle__changes">
        <b
          className={
            event.changeFromDiscoveryPct === null
              ? undefined
              : event.changeFromDiscoveryPct >= 0
                ? "value-up"
                : "value-down"
          }
        >
          {event.isEpisodeStart
            ? directConfirmation
              ? "Episode baseline · first observed as Confirmed"
              : "Episode baseline · first observed state"
            : `${signed(event.changeFromDiscoveryPct)} from episode start`}
        </b>
        {!event.isEpisodeStart && event.changeFromPreviousPct !== null && (
          <em>
            {signed(event.changeFromPreviousPct)} since{" "}
            {squeezeStateLabel(event.previousState ?? "prior transition")}
          </em>
        )}
      </span>
      <small>{event.reason}</small>
    </button>
  );
}

export function SqueezeLifecycle({
  path,
  selectedDate,
  currency,
  currentMethodologyVersion,
  onSelectDate,
}: {
  path: SqueezePath;
  selectedDate: string;
  currency: string;
  currentMethodologyVersion: string;
  onSelectDate: (date: string) => void;
}) {
  const episodes = buildSqueezeLifecycleEpisodes(path);
  const currentEpisode = episodes.find((episode) => episode.isCurrentEpisode);
  if (!currentEpisode) return null;

  const previousEpisodes = episodes.filter((episode) => !episode.isCurrentEpisode);
  const firstEvent = currentEpisode.events[0]!;
  const directConfirmation = isDirectConfirmation(firstEvent);
  const currentStates = currentEpisode.events.map((event) =>
    squeezeStateLabel(event.state),
  );
  const observedStates = [...new Set(currentStates)];
  const storyTitle = directConfirmation
    ? "Confirmed at first observation"
    : currentStates.length <= 5
      ? `Observed progression: ${currentStates.join(" → ")}`
      : `${currentStates.length} state changes across ${observedStates.join(", ")}`;
  const usesLegacyMethod =
    !currentEpisode.methodologyVersions.includes(currentMethodologyVersion) ||
    currentEpisode.methodologyVersions.some(
      (version) => version !== currentMethodologyVersion,
    );

  return (
    <section className="squeeze-lifecycle" aria-label="Setup journey">
      <header>
        <span>
          <Milestone aria-hidden="true" size={14} />
          <strong>Setup journey</strong>
        </span>
        <small>Current episode · D{currentEpisode.episodeNumber}</small>
      </header>

      <div className="squeeze-lifecycle__story">
        <span className="squeeze-lifecycle__story-heading">
          <strong>{storyTitle}</strong>
          <em>{evidenceLabel(currentEpisode)}</em>
        </span>
        <p>
          {directConfirmation
            ? "Atlas did not record Watch, Forming, or Trigger ready for this episode. It entered the archive directly as Confirmed; missing phases are not inferred."
            : `Atlas recorded ${currentEpisode.events.length} point-in-time state ${
                currentEpisode.events.length === 1 ? "observation" : "changes"
              } from ${currentEpisode.startedOn} through ${currentEpisode.endedOn}.`}
        </p>
      </div>

      {usesLegacyMethod && (
        <div className="squeeze-lifecycle__method-warning" role="note">
          <ShieldAlert aria-hidden="true" size={14} />
          <span>
            <strong>Legacy methodology boundary</strong>
            <small>
              This episode used {methodologyLabel(currentEpisode)}. The current engine is{" "}
              {currentMethodologyVersion}. Atlas preserves the archived classification instead
              of silently recomputing it under newer rules.
            </small>
          </span>
        </div>
      )}

      <div className="squeeze-lifecycle__events">
        {currentEpisode.events.map((event) => (
          <EventButton
            code={path.entry.code}
            currency={currency}
            event={event}
            key={`${event.episodeNumber}:${event.date}:${event.state}`}
            onSelectDate={onSelectDate}
            selectedDate={selectedDate}
          />
        ))}
      </div>

      {previousEpisodes.length > 0 && (
        <details className="squeeze-lifecycle__prior">
          <summary>
            <span>
              <History aria-hidden="true" size={13} />
              <strong>Earlier episodes ({previousEpisodes.length})</strong>
            </span>
            <small>Kept separate from D{currentEpisode.episodeNumber}</small>
          </summary>
          <p>
            These are earlier, independent setup episodes for the same ticker. Their price
            changes reset at each episode start and are not part of the current confirmation.
          </p>
          <div className="squeeze-lifecycle__prior-list">
            {previousEpisodes
              .slice()
              .reverse()
              .map((episode) => (
                <section
                  className="squeeze-lifecycle__prior-episode"
                  key={episode.episodeNumber}
                >
                  <header>
                    <span>
                      <strong>Episode D{episode.episodeNumber}</strong>
                      <small>
                        {episode.startedOn}
                        {episode.endedOn !== episode.startedOn
                          ? ` → ${episode.endedOn}`
                          : ""}
                      </small>
                    </span>
                    <em>
                      {evidenceLabel(episode)} · {methodologyLabel(episode)}
                    </em>
                  </header>
                  <div className="squeeze-lifecycle__events squeeze-lifecycle__events--prior">
                    {episode.events.map((event) => (
                      <EventButton
                        code={path.entry.code}
                        currency={currency}
                        event={event}
                        key={`${event.episodeNumber}:${event.date}:${event.state}`}
                        onSelectDate={onSelectDate}
                        selectedDate={selectedDate}
                      />
                    ))}
                  </div>
                </section>
              ))}
          </div>
        </details>
      )}
    </section>
  );
}
