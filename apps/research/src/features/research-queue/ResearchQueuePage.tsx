import { BriefcaseBusiness, CircleAlert, RefreshCw, SlidersHorizontal } from "lucide-react";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { isResearchPreview, researchDeployment } from "../../app/deployment";
import {
  Button,
  SearchInput,
  SegmentedControl,
  SelectField,
  StatusBadge,
  type SelectOption,
} from "../../design-system";
import {
  filterResearchQueue,
  summarizeResearchQueue,
  type CapTier,
  type CapTierFilter,
  type QueueStatusFilter,
  type ResearchCandidate,
} from "./model";
import { QueueSummaryStrip } from "./QueueSummaryStrip";
import { ResearchInspector } from "./ResearchInspector";
import { ResearchQueueTable } from "./ResearchQueueTable";
import {
  useResearchQueue,
  useResearchWorkspaces,
} from "./useResearchQueue";

const CAP_LABELS: Record<CapTier, string> = {
  mega: "Mega cap",
  large: "Large cap",
  mid: "Mid cap",
  small: "Small cap",
  micro: "Micro cap",
  penny: "Penny stock",
  unclassified: "Unclassified",
};

const CAP_OPTIONS: readonly SelectOption<CapTierFilter>[] = [
  { value: "all", label: "All capitalization tiers" },
  ...researchDeployment.capTiers.map((tier) => ({
    value: tier as CapTier,
    label: CAP_LABELS[tier as CapTier],
  })),
];

function formatCutoff(timestamp: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(timestamp));
}

export function ResearchQueuePage() {
  const navigate = useNavigate();
  const workspaces = useResearchWorkspaces();
  const workspace = workspaces.data?.[0];
  const [status, setStatus] = useState<QueueStatusFilter>("all");
  const [capTier, setCapTier] = useState<CapTierFilter>("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const deferredQuery = useDeferredValue(query);
  const queue = useResearchQueue(workspace?.id, { capTier, query: deferredQuery });

  const allCandidates = queue.data?.candidates ?? [];
  const filtered = useMemo(
    () => filterResearchQueue(allCandidates, { capTier, status, query }),
    [allCandidates, capTier, query, status],
  );
  const summary = useMemo(() => summarizeResearchQueue(allCandidates), [allCandidates]);
  const selected = useMemo(
    () => filtered.find((candidate) => candidate.id === selectedId) ?? filtered[0] ?? null,
    [filtered, selectedId],
  );

  useEffect(() => {
    if (selected && selected.id !== selectedId) setSelectedId(selected.id);
    if (!selected && selectedId !== null) setSelectedId(null);
  }, [selected, selectedId]);

  if (workspaces.isLoading || (workspace && queue.isLoading)) {
    return (
      <div aria-label="Loading research queue" className="research-loading">
        <span className="research-loading__header" />
        <span className="research-loading__summary" />
        <span className="research-loading__body" />
      </div>
    );
  }

  if (workspaces.isError || queue.isError) {
    return (
      <section className="research-unavailable">
        <CircleAlert aria-hidden="true" size={26} />
        <h1>Research queue unavailable</h1>
        <p>The secured queue could not be loaded. No preview or stale tenant data was substituted.</p>
        <Button
          onPress={() => (workspaces.isError ? workspaces.refetch() : queue.refetch())}
          variant="secondary"
        >
          <RefreshCw aria-hidden="true" size={15} />
          Retry
        </Button>
      </section>
    );
  }

  if (!workspace) {
    return (
      <section className="research-unavailable">
        <CircleAlert aria-hidden="true" size={26} />
        <h1>Research workspace unavailable</h1>
        <p>No workspace was returned for this {researchDeployment.exchangeName} account.</p>
        <Button onPress={() => workspaces.refetch()} variant="primary">
          <RefreshCw aria-hidden="true" size={15} />
          Retry provisioning
        </Button>
      </section>
    );
  }

  return (
    <div className="research-queue-page">
      <header className="queue-page-header">
        <div>
          <span className="queue-page-header__eyebrow">
            {workspace.organizationName} · {researchDeployment.exchangeName}
          </span>
          <h1>Research queue</h1>
          <p>Ranked by investigation urgency from traceable evidence, factor changes, and implementation risk.</p>
        </div>
        <div className="queue-page-header__actions">
          <Button onPress={() => navigate("/portfolio")} variant="secondary">
            <BriefcaseBusiness aria-hidden="true" size={14} />
            Open strategy book
          </Button>
          <span className="queue-page-header__cutoff">
            Knowledge cutoff
            <strong>{queue.data ? formatCutoff(queue.data.knowledgeCutoffAt) : "—"}</strong>
          </span>
        </div>
      </header>

      <QueueSummaryStrip summary={summary} />

      <section className="queue-controls" aria-label="Research queue filters">
        <div className="queue-controls__primary">
          <SegmentedControl
            label="Workflow status"
            onChange={setStatus}
            options={[
              { value: "all", label: "All" },
              { value: "new_evidence", label: "Recent evidence", count: summary.newEvidence },
              { value: "needs_review", label: "Needs review", count: summary.needsReview },
              { value: "monitoring", label: "Monitoring" },
            ]}
            value={status}
          />
        </div>
        <div className="queue-controls__secondary">
          <SearchInput
            aria-label="Search research queue"
            onChange={setQuery}
            placeholder="Search ticker, company, sector, or reason"
            value={query}
          />
          <span className="queue-controls__cap-filter">
            <SlidersHorizontal aria-hidden="true" size={15} />
            <SelectField
              label="Capitalization mandate"
              onChange={setCapTier}
              options={CAP_OPTIONS}
              value={capTier}
            />
          </span>
        </div>
      </section>

      <div className="queue-results-meta">
        <span>
          <strong className="tnum">{filtered.length}</strong>
          {queue.data?.isTruncated
            ? ` shown from ${queue.data.eligibleCount} eligible securities`
            : " securities in this view"}
        </span>
        <span>
          <StatusBadge tone={isResearchPreview ? "warning" : "positive"} dot>
            {isResearchPreview ? "Illustrative preview" : "Tenant-verified data"}
          </StatusBadge>
          Urgency can rise because evidence is new or risk is high. It is not a buy score.
        </span>
      </div>

      <div className="queue-workbench">
        <section aria-label="Ranked research securities" className="queue-workbench__table">
          <ResearchQueueTable
            candidates={filtered}
            onSelect={(candidate: ResearchCandidate) => setSelectedId(candidate.id)}
            selectedId={selected?.id ?? null}
          />
        </section>
        <ResearchInspector candidate={selected} />
      </div>
    </div>
  );
}
