import {
  AlertTriangle,
  Check,
  Clock3,
  DatabaseZap,
  History,
  Play,
  RefreshCw,
  Save,
  Workflow,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { researchDeployment } from "../../app/deployment";
import { Button, SelectField, StatusBadge } from "../../design-system";
import { useResearchWorkspaces } from "../research-queue/useResearchQueue";
import {
  useAutomationPolicy,
  useConfigureAutomation,
  useResearchRun,
  useResearchRuns,
  useRunLifecycle,
} from "./hooks";
import { lifecycleRunDelta } from "./model";

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

function money(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: researchDeployment.currency,
    maximumFractionDigits: 2,
  }).format(value);
}

function targetAction(value: string): string {
  return value.replace("_target", "").replace("_", " ");
}

export function LifecycleControlPage() {
  const navigate = useNavigate();
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
  const [selectedRunId, setSelectedRunId] = useState("");

  useEffect(() => {
    if (!policy.data) return;
    setEnabled(policy.data.enabled);
    setCapTier(policy.data.capTier ?? "all");
    setQueueLimit(policy.data.queueLimit);
    setResearchLimit(policy.data.researchLimit);
    setUniverseLimit(policy.data.universeLimit);
    setInitialCapital(policy.data.initialCapital);
  }, [policy.data]);

  const lifecycleRuns = useMemo(
    () => runs.data?.filter((run) => run.runKind === "lifecycle") ?? [],
    [runs.data],
  );
  const listedLifecycle = lifecycleRuns.find((run) => run.id === selectedRunId) ?? lifecycleRuns[0];
  const runDetail = useResearchRun(workspace?.id, listedLifecycle?.id);
  const selectedLifecycle = runDetail.data ?? listedLifecycle;
  const steps = new Map(selectedLifecycle?.steps.map((step) => [step.kind, step]));
  const summary = selectedLifecycle?.parameters.summary as Record<string, unknown> | undefined;
  const delta = useMemo(() => lifecycleRunDelta(selectedLifecycle), [selectedLifecycle]);
  const shadowStep = steps.get("forward_shadow_reconciliation");
  const paperDeltaAvailable = Boolean(
    shadowStep && Object.prototype.hasOwnProperty.call(shadowStep.output, "new_execution_count"),
  );
  const calibrationStep = steps.get("outcome_calibration");
  const calibrationDeltaAvailable = Boolean(
    calibrationStep && Object.prototype.hasOwnProperty.call(calibrationStep.output, "newly_matured"),
  );
  const researched = delta.researchChanges.filter((item) => item.action === "researched");
  const unchangedResearch = delta.researchChanges.filter((item) => item.action === "unchanged").length;
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
    return <section className="research-unavailable"><DatabaseZap size={26} /><h1>Automation and audit unavailable</h1><p>The tenant-bound automation policy or run ledger could not be loaded.</p><Button onPress={() => { void policy.refetch(); void runs.refetch(); }}><RefreshCw size={14} />Retry</Button></section>;
  }

  return (
    <div className="atlas-page">
      <header className="atlas-page-header">
        <div><span className="atlas-page-header__eyebrow">Operations · registered process · completed market sessions only</span><h1>Automation and audit</h1><p>Configure the post-close process and inspect its immutable run ledger. This is an operator surface, not an investment-decision screen.</p></div>
        <span className="atlas-page-header__actions">
          <Button onPress={() => navigate("/memory")} variant="secondary"><History size={14} />Research memory</Button>
          <StatusBadge tone={statusTone(policy.data?.lastRunStatus)} dot>{policy.data?.lastRunStatus ?? "not configured"}</StatusBadge>
        </span>
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
            <header><Clock3 aria-hidden="true" size={16} /><span><strong>Lifecycle run</strong><small>{selectedLifecycle ? displayDate(selectedLifecycle.requestedAt) : "No lifecycle run recorded"}</small></span>{lifecycleRuns.length > 0 && <SelectField label="Lifecycle history" onChange={setSelectedRunId} options={lifecycleRuns.map((run) => ({ value: run.id, label: `${displayDate(run.requestedAt)} · ${run.status}` }))} value={listedLifecycle?.id ?? ""} />}{selectedLifecycle && <StatusBadge tone={statusTone(selectedLifecycle.status)}>{selectedLifecycle.status}</StatusBadge>}</header>
            <div className="lifecycle-stages">
              {STAGES.map(([key, label], index) => {
                const step = steps.get(key);
                return <div className={`lifecycle-stage lifecycle-stage--${step?.status ?? "pending"}`} key={key}><span>{step?.status === "succeeded" ? <Check size={13} /> : index + 1}</span><strong>{label}</strong><small>{step?.status ?? "pending"}</small></div>;
              })}
            </div>
            {selectedLifecycle && <div className="lifecycle-summary">
              <span><small>Queue selected</small><strong>{typeof summary?.queue_selected === "number" ? summary.queue_selected : "—"}</strong></span>
              <span><small>Backtest</small><strong>{typeof summary?.backtest_validation_status === "string" ? summary.backtest_validation_status.replace(/_/g, " ") : "—"}</strong></span>
              <span><small>Paper gate</small><strong>{typeof summary?.promotion_status === "string" ? summary.promotion_status : "—"}</strong></span>
              <span><small>Matured outcomes</small><strong>{typeof summary?.calibration_matured === "number" ? summary.calibration_matured : "—"}</strong></span>
            </div>}
          </section>

          {selectedLifecycle && <section className="atlas-panel lifecycle-changes">
            <header><History aria-hidden="true" size={16} /><span><strong>What changed in this run</strong><small>Only deltas created by this lifecycle · targets are not executions</small></span></header>
            <div className="lifecycle-change-kpis">
              <span><small>Research updated</small><strong>{researched.length}</strong></span>
              <span><small>Sessions advanced</small><strong>{paperDeltaAvailable ? delta.sessionsAdvanced : "—"}</strong></span>
              <span><small>Paper executions</small><strong>{paperDeltaAvailable ? delta.executions.length : "—"}</strong></span>
              <span><small>Outcomes matured</small><strong>{calibrationDeltaAvailable ? delta.calibrationMatured : "—"}</strong></span>
            </div>
            <div className="lifecycle-change-grid">
              <div>
                <h3>Research evidence changes</h3>
                {researched.length > 0 ? <div className="lifecycle-change-list">{researched.map((item) => <span key={item.ticker}><strong>{item.ticker}</strong><small>{item.status}</small></span>)}</div> : <p>No company evidence changed enough to create a new research run.</p>}
                {unchangedResearch > 0 && <small>{unchangedResearch} selected {unchangedResearch === 1 ? "company was" : "companies were"} unchanged and reused.</small>}
              </div>
              <div>
                <h3>Paper fills created</h3>
                {!paperDeltaAvailable ? <p>This historical run predates per-run execution deltas. Its complete fills remain in Portfolio intelligence → Execution ledger.</p> : delta.executions.length > 0 ? <div className="lifecycle-change-list">{delta.executions.map((trade) => <span key={trade.id}><strong>{trade.side.toUpperCase()} {trade.code}</strong><small>{trade.quantity.toLocaleString()} @ {money(trade.fillPrice)} · {trade.date}</small></span>)}</div> : <p>No paper trade was created by this run.</p>}
              </div>
              <div>
                <h3>Next-session target changes</h3>
                {!paperDeltaAvailable ? <p>Target deltas were not retained for this historical run.</p> : delta.targetChanges.length > 0 ? <div className="lifecycle-change-list">{delta.targetChanges.map((change, index) => <span key={`${change.date}:${change.sessionNumber}:${change.code}:${index}`}><strong>{change.code} · {targetAction(change.action)}</strong><small>{(change.previousWeight * 100).toFixed(1)}% → {(change.targetWeight * 100).toFixed(1)}% · {change.date}</small></span>)}</div> : <p>No target weight changed in this run.</p>}
              </div>
              <div>
                <h3>Risk actions</h3>
                <p>{!paperDeltaAvailable ? "Per-run risk deltas were not retained for this historical run." : delta.riskInterventions > 0 ? `${delta.riskInterventions} risk intervention${delta.riskInterventions === 1 ? "" : "s"} recorded.` : "No risk intervention fired in this run."}</p>
              </div>
            </div>
          </section>}

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
