import { CalendarDays, CircleAlert, RefreshCw } from "lucide-react";
import { useDeferredValue, useMemo, useState } from "react";

import { isResearchPreview, researchDeployment } from "../../app/deployment";
import {
  Button,
  SearchInput,
  SegmentedControl,
  SelectField,
  StatusBadge,
  type SelectOption,
} from "../../design-system";
import { useResearchWorkspaces } from "../research-queue/useResearchQueue";
import {
  HORIZON_OPTIONS,
  confidenceLabel,
  eventTypeLabel,
  filterEvents,
  groupByDate,
  timingLabel,
  type HorizonDays,
} from "./model";
import { useCatalystCalendar } from "./useCatalystCalendar";
import "./catalyst-calendar.css";

const EVENT_TYPE_OPTIONS: readonly SelectOption<string>[] = [
  { value: "all", label: "All event types" },
  { value: "record_date", label: "Record dates" },
  { value: "agm", label: "AGMs" },
  { value: "egm", label: "EGMs" },
  { value: "board_meeting", label: "Board meetings" },
  { value: "spot_window", label: "Spot windows" },
  { value: "periodic_report_window", label: "Expected reports" },
];

function formatDay(date: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(`${date}T00:00:00Z`));
}

export function CatalystCalendarPage() {
  const workspaces = useResearchWorkspaces();
  const workspace = workspaces.data?.[0];
  const [horizonDays, setHorizonDays] = useState<HorizonDays>(60);
  const [eventType, setEventType] = useState("all");
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const calendar = useCatalystCalendar(workspace?.id, { horizonDays });

  const events = useMemo(
    () => filterEvents(calendar.data?.events ?? [], { code: deferredQuery, eventType }),
    [calendar.data?.events, deferredQuery, eventType],
  );
  const groups = useMemo(() => groupByDate(events), [events]);
  const isLoading = workspaces.isPending || calendar.isPending;
  const error = workspaces.error ?? calendar.error;

  return (
    <section className="catalyst-calendar" aria-labelledby="catalyst-calendar-title">
      <header className="catalyst-calendar__header">
        <div>
          <h1 id="catalyst-calendar-title">
            <CalendarDays aria-hidden="true" size={20} /> Catalyst calendar
          </h1>
          <p>
            Dated official events and inferred report windows for {researchDeployment.market}.
            Confidence is explicit: an inferred window is never presented as a confirmed date, and
            a name with no supported event simply does not appear.
          </p>
        </div>
        {isResearchPreview ? (
          <StatusBadge tone="warning">Preview records — illustrative only</StatusBadge>
        ) : null}
      </header>

      <div className="catalyst-calendar__controls">
        <SegmentedControl
          label="Calendar horizon"
          value={String(horizonDays)}
          onChange={(value) => setHorizonDays(Number(value) as HorizonDays)}
          options={HORIZON_OPTIONS.map((days) => ({
            value: String(days),
            label: `${days}d`,
          }))}
        />
        <SelectField
          label="Event type"
          value={eventType}
          onChange={setEventType}
          options={EVENT_TYPE_OPTIONS}
        />
        <SearchInput
          aria-label="Filter by ticker"
          placeholder="Filter by ticker…"
          value={query}
          onChange={setQuery}
        />
        <Button
          variant="quiet"
          onPress={() => void calendar.refetch()}
          isDisabled={calendar.isFetching}
        >
          <RefreshCw aria-hidden="true" size={16} />
          Refresh
        </Button>
      </div>

      {error ? (
        <div role="alert" className="catalyst-calendar__error">
          <CircleAlert aria-hidden="true" size={18} />
          {error instanceof Error ? error.message : "The catalyst calendar failed to load."}
        </div>
      ) : null}

      {isLoading ? <p className="catalyst-calendar__empty">Loading catalyst events…</p> : null}

      {!isLoading && !error && groups.length === 0 ? (
        <p className="catalyst-calendar__empty">
          No catalyst events inside the selected horizon. That is an honest empty state — events
          appear only when an official source or filing cadence supports them.
        </p>
      ) : null}

      <ol className="catalyst-calendar__days">
        {groups.map((group) => (
          <li key={group.date} className="catalyst-calendar__day">
            <h2>{formatDay(group.date)}</h2>
            <ul>
              {group.events.map((event) => (
                <li
                  key={event.id}
                  className={`catalyst-event catalyst-event--${event.timingKind}`}
                >
                  <div className="catalyst-event__head">
                    <span className="catalyst-event__ticker">{event.code}</span>
                    <span className="catalyst-event__type">{eventTypeLabel(event.eventType)}</span>
                    <StatusBadge
                      tone={event.confidence === "official_confirmed" ? "positive" : "warning"}
                    >
                      {confidenceLabel(event.confidence)}
                    </StatusBadge>
                  </div>
                  <p className="catalyst-event__timing">{timingLabel(event)}</p>
                  {event.expectedEvidence ? (
                    <p className="catalyst-event__evidence">{event.expectedEvidence}</p>
                  ) : null}
                  <p className="catalyst-event__source">
                    Source: {event.sourceType.split("_").join(" ")} · known{" "}
                    {event.knownAt.slice(0, 10)}
                  </p>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </section>
  );
}
