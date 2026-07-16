import { researchDeployment } from "../../app/deployment";
import type { CatalystEvent } from "./model";

function iso(daysFromNow: number): string {
  const date = new Date();
  date.setDate(date.getDate() + daysFromNow);
  return date.toISOString().slice(0, 10);
}

const DSE_EVENTS: CatalystEvent[] = [
  {
    id: "prev-dse-1",
    code: "GP",
    eventType: "record_date",
    title: "GP record date",
    timingKind: "confirmed",
    confirmedDate: iso(4),
    windowStart: null,
    windowEnd: null,
    status: "scheduled",
    confidence: "official_confirmed",
    sourceType: "dse_announcement",
    sourceRef: "announcement:preview-1",
    sourceUrl: null,
    knownAt: new Date().toISOString(),
    expectedEvidence: "Entitlement snapshot; verify shareholder position changes afterwards.",
    details: { category: "corporate_action" },
  },
  {
    id: "prev-dse-2",
    code: "BRACBANK",
    eventType: "agm",
    title: "BRACBANK annual general meeting",
    timingKind: "confirmed",
    confirmedDate: iso(12),
    windowStart: null,
    windowEnd: null,
    status: "scheduled",
    confidence: "official_confirmed",
    sourceType: "dse_announcement",
    sourceRef: "announcement:preview-2",
    sourceUrl: null,
    knownAt: new Date().toISOString(),
    expectedEvidence: "AGM outcome: dividend approval, board changes, shareholder resolutions.",
    details: { category: "agm" },
  },
];

const US_EVENTS: CatalystEvent[] = [
  {
    id: "prev-us-1",
    code: "NVDA",
    eventType: "periodic_report_window",
    title: "NVDA expected periodic report",
    timingKind: "window",
    confirmedDate: null,
    windowStart: iso(6),
    windowEnd: iso(30),
    status: "scheduled",
    confidence: "inferred_cadence",
    sourceType: "sec_filing_cadence",
    sourceRef: "acc-preview-1",
    sourceUrl: null,
    knownAt: new Date().toISOString(),
    expectedEvidence:
      "Next 10-K/10-Q: revenue and margin trajectory, liquidity, share count, and language changes.",
    details: { cadence_days: 91, observed_filings: 12 },
  },
  {
    id: "prev-us-2",
    code: "TFIN",
    eventType: "periodic_report_window",
    title: "TFIN expected periodic report",
    timingKind: "window",
    confirmedDate: null,
    windowStart: iso(2),
    windowEnd: iso(26),
    status: "scheduled",
    confidence: "inferred_cadence",
    sourceType: "sec_filing_cadence",
    sourceRef: "acc-preview-2",
    sourceUrl: null,
    knownAt: new Date().toISOString(),
    expectedEvidence:
      "Next 10-Q: loan growth, credit costs, and any change in going-concern or control language.",
    details: { cadence_days: 91, observed_filings: 8 },
  },
];

export const demoCatalystEvents: CatalystEvent[] =
  researchDeployment.market === "DSE" ? DSE_EVENTS : US_EVENTS;
