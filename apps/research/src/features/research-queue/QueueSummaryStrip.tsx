import {
  AlertTriangle,
  CalendarClock,
  FileDiff,
  ListChecks,
} from "lucide-react";

import type { QueueSummary } from "./model";

const items = [
  { key: "total", label: "Research backlog", icon: ListChecks, tone: "neutral" },
  { key: "newEvidence", label: "Recent records", icon: FileDiff, tone: "info" },
  { key: "needsReview", label: "Needs review", icon: AlertTriangle, tone: "warning" },
  { key: "catalystSevenDays", label: "Catalysts · 7d", icon: CalendarClock, tone: "positive" },
] as const;

export function QueueSummaryStrip({ summary }: { summary: QueueSummary }) {
  return (
    <section aria-label="Research queue summary" className="queue-summary">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <div className={`queue-summary__item queue-summary__item--${item.tone}`} key={item.key}>
            <Icon aria-hidden="true" size={17} strokeWidth={1.8} />
            <span>
              <strong className="tnum">{summary[item.key]}</strong>
              <small>{item.label}</small>
            </span>
          </div>
        );
      })}
      <div className="queue-summary__coverage">
        <span>
          Evidence gaps <strong className="tnum">{summary.evidenceGaps}</strong>
        </span>
        <div aria-hidden="true" className="queue-summary__coverage-track">
          <span style={{ width: `${Math.max(8, 100 - summary.evidenceGaps * 14)}%` }} />
        </div>
      </div>
    </section>
  );
}
