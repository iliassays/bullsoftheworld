import { BrainCircuit, Clock3, DatabaseZap, RefreshCw } from "lucide-react";

import { Button, StatusBadge } from "../../design-system";
import { useResearchWorkspaces } from "../research-queue/useResearchQueue";
import { useCalibration, useResearchRuns } from "./hooks";

function tone(status: string): "positive" | "warning" | "negative" | "neutral" {
  if (status === "qualified" || status === "succeeded") return "positive";
  if (status === "monitor" || status === "pending") return "warning";
  if (status === "rejected") return "negative";
  return "neutral";
}

export function ResearchMemoryPage() {
  const workspace = useResearchWorkspaces().data?.[0];
  const runs = useResearchRuns(workspace?.id);
  const calibration = useCalibration(workspace?.id);
  const failed = runs.isError || calibration.isError;

  if (failed) return <section className="research-unavailable"><DatabaseZap size={26} /><h1>Research memory unavailable</h1><p>The immutable run ledger or forward observations could not be loaded.</p><Button onPress={() => { void runs.refetch(); void calibration.refetch(); }}><RefreshCw size={14} />Retry</Button></section>;

  return (
    <div className="atlas-page">
      <header className="atlas-page-header"><div><span className="atlas-page-header__eyebrow">Immutable decisions · outcome calibration · no hindsight rewrite</span><h1>Research memory</h1><p>Every autonomous verdict remains tied to its original evidence cutoff, while future returns mature in a separate observation ledger.</p></div>{calibration.data && <StatusBadge tone="info" dot>{calibration.data.matured} matured · {calibration.data.pending} pending</StatusBadge>}</header>

      <div className="memory-grid">
        <section className="atlas-panel">
          <header><BrainCircuit size={16} /><span><strong>Forward calibration</strong><small>Descriptive outcomes, not proof of causality</small></span></header>
          <div className="calibration-table">
            <div><span>Original verdict</span><span>Horizon</span><span>Samples</span><span>Mean return</span><span>Positive rate</span></div>
            {(calibration.data?.buckets ?? []).map((bucket) => <div key={`${bucket.signalStatus}-${bucket.horizonSessions}`}><StatusBadge tone={tone(bucket.signalStatus)}>{bucket.signalStatus}</StatusBadge><span>{bucket.horizonSessions} sessions</span><span>{bucket.observations}</span><span className={bucket.averageReturnPct >= 0 ? "value-up" : "value-down"}>{bucket.averageReturnPct.toFixed(2)}%</span><span>{bucket.positiveRatePct.toFixed(1)}%</span></div>)}
            {calibration.data?.buckets.length === 0 && <p>No horizon has matured yet. Atlas will not manufacture a success rate from incomplete observations.</p>}
          </div>
        </section>

        <section className="atlas-panel">
          <header><Clock3 size={16} /><span><strong>Run ledger</strong><small>Latest 50 tenant-bound research records</small></span></header>
          <div className="run-ledger">
            {(runs.data ?? []).map((run) => {
              const decision = typeof run.parameters.decision === "object" && run.parameters.decision !== null ? run.parameters.decision as Record<string, unknown> : null;
              const decisionStatus = typeof decision?.status === "string" ? decision.status : run.status;
              const label = run.code ?? (typeof run.parameters.strategy_key === "string" ? run.parameters.strategy_key : "Portfolio experiment");
              return <article key={run.id}><span><strong>{label}</strong><small>{run.runKind.replace(/_/g, " ")} · {new Date(run.requestedAt).toLocaleString()}</small></span><StatusBadge tone={tone(decisionStatus)}>{decisionStatus}</StatusBadge><code>{run.codeVersion}</code></article>;
            })}
            {runs.data?.length === 0 && <p>No autonomous research record has been created in this workspace.</p>}
          </div>
        </section>
      </div>
    </div>
  );
}
