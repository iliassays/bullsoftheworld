import {
  AlertTriangle,
  Check,
  Clock3,
  DatabaseZap,
  Play,
  RefreshCw,
  Save,
  Workflow,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { researchDeployment } from "../../app/deployment";
import { Button, SelectField, StatusBadge } from "../../design-system";
import { useResearchWorkspaces } from "../research-queue/useResearchQueue";
import {
  useAutomationPolicy,
  useConfigureAutomation,
  useResearchRuns,
  useRunLifecycle,
} from "./hooks";

const CAP_OPTIONS = [
  { value: "all", label: "All capitalizations" },
  { value: "mega", label: "Mega cap" },
  { value: "large", label: "Large cap" },
  { value: "mid", label: "Mid cap" },
  { value: "small", label: "Small cap" },
  { value: "micro", label: "Micro cap" },
  { value: "penny", label: "Penny" },
] as const;

const STAGES = [
  ["queue_selection", "Queue"],
  ["evidence_changed_research", "Research"],
  ["registered_backtest", "Backtest"],
  ["forward_shadow_reconciliation", "Shadow book"],
  ["outcome_calibration", "Calibration"],
] as const;

function displayDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "Not scheduled";
}

function statusTone(status: string | null | undefined) {
  if (status === "succeeded") return "positive" as const;
  if (status === "failed") return "negative" as const;
  if (status === "queued" || status === "running") return "warning" as const;
  return "neutral" as const;
}

export function LifecycleControlPage() {
  const workspace = useResearchWorkspaces().data?.[0];
  const policy = useAutomationPolicy(workspace?.id);
  const runs = useResearchRuns(workspace?.id);
  const configure = useConfigureAutomation(workspace?.id);
  const dispatch = useRunLifecycle(workspace?.id);
  const strategyKey = researchDeployment.market === "DSE" ? "dse_reversal_v1" : "us_breakout_v1";
  const [enabled, setEnabled] = useState(false);
  const [capTier, setCapTier] = useState("all");
  const [queueLimit, setQueueLimit] = useState(20);
  const [researchLimit, setResearchLimit] = useState(5);
  const [universeLimit, setUniverseLimit] = useState(25);
  const [initialCapital, setInitialCapital] = useState(
    researchDeployment.market === "DSE" ? 10_000_000 : 100_000,
  );

  useEffect(() => {
    if (!policy.data) return;
    setEnabled(policy.data.enabled);
    setCapTier(policy.data.capTier ?? "all");
    setQueueLimit(policy.data.queueLimit);
    setResearchLimit(policy.data.researchLimit);
    setUniverseLimit(policy.data.universeLimit);
    setInitialCapital(policy.data.initialCapital);
  }, [policy.data]);

  const latestLifecycle = useMemo(
    () => runs.data?.find((run) => run.runKind === "lifecycle"),
    [runs.data],
  );
  const steps = new Map(latestLifecycle?.steps.map((step) => [step.kind, step]));
  const summary = latestLifecycle?.parameters.summary as Record<string, unknown> | undefined;
  const invalidLimits = researchLimit > queueLimit;
  const failed = policy.isError || runs.isError;

  const save = () => configure.mutate({
    enabled,
    queue_limit: queueLimit,
    research_limit: researchLimit,
    cap_tier: capTier === "all" ? null : capTier,
    strategy_key: strategyKey,
    universe_limit: universeLimit,
    initial_capital: initialCapital,
  });

  if (failed) {
    return <section className="research-unavailable"><DatabaseZap size={26} /><h1>Lifecycle control unavailable</h1><p>The tenant-bound automation policy or run ledger could not be loaded.</p><Button onPress={() => { void policy.refetch(); void runs.refetch(); }}><RefreshCw size={14} />Retry</Button></section>;
  }

  return (
    <div className="atlas-page">
      <header className="atlas-page-header">
        <div><span className="atlas-page-header__eyebrow">Registered process · completed market sessions only</span><h1>Lifecycle control</h1><p>Queue, research, backtest, forward paper book, calibration, and objective promotion gates.</p></div>
        <StatusBadge tone={statusTone(policy.data?.lastRunStatus)} dot>{policy.data?.lastRunStatus ?? "not configured"}</StatusBadge>
      </header>

      <div className="lifecycle-layout">
        <aside className="atlas-panel lifecycle-policy">
          <header><Workflow aria-hidden="true" size={16} /><span><strong>Automation policy</strong><small>{researchDeployment.market} workspace only</small></span></header>
          <div className="lifecycle-toggle-row">
            <span><strong>Post-close automation</strong><small>Next slot: {displayDate(policy.data?.nextRunAt)}</small></span>
            <button aria-checked={enabled} aria-label="Post-close automation" className="lifecycle-toggle" onClick={() => setEnabled((value) => !value)} role="switch" type="button"><span /></button>
          </div>
          <label>Research mandate<SelectField label="Research mandate" onChange={setCapTier} options={CAP_OPTIONS} value={capTier} /></label>
          <label>Registered strategy<input disabled value={strategyKey} /></label>
          <span className="lifecycle-policy__split">
            <label>Queue reviewed<input max="50" min="1" onChange={(event) => setQueueLimit(Number(event.target.value))} type="number" value={queueLimit} /></label>
            <label>Companies researched<input max="20" min="1" onChange={(event) => setResearchLimit(Number(event.target.value))} type="number" value={researchLimit} /></label>
          </span>
          <label>Backtest universe<input max="30" min="5" onChange={(event) => setUniverseLimit(Number(event.target.value))} type="number" value={universeLimit} /></label>
          <label>Paper capital ({researchDeployment.currency})<input min="1" onChange={(event) => setInitialCapital(Number(event.target.value))} type="number" value={initialCapital} /></label>
          {invalidLimits && <p className="atlas-error"><AlertTriangle size={13} />Companies researched cannot exceed the reviewed queue.</p>}
          <div className="lifecycle-policy__actions">
            <Button isDisabled={!workspace || invalidLimits || configure.isPending} onPress={save} variant="primary"><Save aria-hidden="true" size={14} />{configure.isPending ? "Saving…" : "Save policy"}</Button>
            <Button isDisabled={!policy.data || dispatch.isPending} onPress={() => dispatch.mutate()}><Play aria-hidden="true" size={14} />{dispatch.isPending ? "Dispatching…" : "Run now"}</Button>
          </div>
          {configure.isSuccess && <p className="atlas-success"><Check size={13} />Policy saved and audit logged.</p>}
          {(configure.isError || dispatch.isError) && <p className="atlas-error"><AlertTriangle size={13} />{configure.error?.message ?? dispatch.error?.message}</p>}
        </aside>

        <main className="lifecycle-main">
          <section className="atlas-panel lifecycle-status">
            <header><Clock3 aria-hidden="true" size={16} /><span><strong>Latest lifecycle</strong><small>{latestLifecycle ? displayDate(latestLifecycle.requestedAt) : "No lifecycle run recorded"}</small></span>{latestLifecycle && <StatusBadge tone={statusTone(latestLifecycle.status)}>{latestLifecycle.status}</StatusBadge>}</header>
            <div className="lifecycle-stages">
              {STAGES.map(([key, label], index) => {
                const step = steps.get(key);
                return <div className={`lifecycle-stage lifecycle-stage--${step?.status ?? "pending"}`} key={key}><span>{step?.status === "succeeded" ? <Check size={13} /> : index + 1}</span><strong>{label}</strong><small>{step?.status ?? "pending"}</small></div>;
              })}
            </div>
            {latestLifecycle && <div className="lifecycle-summary">
              <span><small>Queue selected</small><strong>{typeof summary?.queue_selected === "number" ? summary.queue_selected : "—"}</strong></span>
              <span><small>Backtest</small><strong>{typeof summary?.backtest_validation_status === "string" ? summary.backtest_validation_status.replace(/_/g, " ") : "—"}</strong></span>
              <span><small>Paper gate</small><strong>{typeof summary?.promotion_status === "string" ? summary.promotion_status : "—"}</strong></span>
              <span><small>Matured outcomes</small><strong>{typeof summary?.calibration_matured === "number" ? summary.calibration_matured : "—"}</strong></span>
            </div>}
          </section>

          <section className="atlas-panel lifecycle-guardrails">
            <header><DatabaseZap aria-hidden="true" size={16} /><span><strong>Decision boundary</strong><small>No broker integration</small></span></header>
            <dl><div><dt>Data boundary</dt><dd>{researchDeployment.tenant} · {researchDeployment.market}</dd></div><div><dt>Forward evidence</dt><dd>60 completed sessions minimum</dd></div><div><dt>Capital action</dt><dd>None; eligibility is not execution</dd></div><div><dt>Last completion</dt><dd>{displayDate(policy.data?.lastCompletedAt)}</dd></div></dl>
            {policy.data?.lastError && <p className="portfolio-stop"><AlertTriangle size={14} /><span><strong>Last run failed</strong>{policy.data.lastError}</span></p>}
          </section>
        </main>
      </div>
    </div>
  );
}
