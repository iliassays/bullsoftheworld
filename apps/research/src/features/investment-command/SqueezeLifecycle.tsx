import { ChevronRight, Milestone } from "lucide-react";

import type { SqueezePath } from "../../app/api-client";
import { StatusBadge } from "../../design-system";
import { buildSqueezeLifecycle } from "./squeeze-lifecycle";
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

export function SqueezeLifecycle({
  path,
  selectedDate,
  currency,
  onSelectDate,
}: {
  path: SqueezePath;
  selectedDate: string;
  currency: string;
  onSelectDate: (date: string) => void;
}) {
  const events = buildSqueezeLifecycle(path);
  if (events.length === 0) return null;

  return (
    <section className="squeeze-lifecycle" aria-label="Setup lifecycle">
      <header>
        <span>
          <Milestone aria-hidden="true" size={14} />
          <strong>Setup lifecycle</strong>
        </span>
        <small>Point-in-time transitions</small>
      </header>
      <div className="squeeze-lifecycle__events">
        {events.map((event) => {
          const isDiscovery =
            event.date === path.entry.firstDiscoveredOn ||
            event.previousState === null ||
            event.previousState === "none";
          const current = event.date === selectedDate;
          return (
            <button
              aria-current={current ? "date" : undefined}
              aria-label={`Open ${event.date} archived snapshot for ${path.entry.code}`}
              key={`${event.date}:${event.state}`}
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
                  {isDiscovery
                    ? "Discovery baseline"
                    : `${signed(event.changeFromDiscoveryPct)} from discovery`}
                </b>
                {!isDiscovery && event.changeFromPreviousPct !== null && (
                  <em>
                    {signed(event.changeFromPreviousPct)} since{" "}
                    {squeezeStateLabel(event.previousState ?? "prior transition")}
                  </em>
                )}
              </span>
              <small>{event.reason}</small>
            </button>
          );
        })}
      </div>
    </section>
  );
}
