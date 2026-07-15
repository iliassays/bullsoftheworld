import { AlertTriangle, FlaskConical, Play, ShieldCheck, TestTube2, WalletCards } from "lucide-react";
import { useMemo, useState } from "react";

import { researchDeployment } from "../../app/deployment";
import { Button, SelectField, StatusBadge, type SelectOption } from "../../design-system";
import { useResearchWorkspaces } from "../research-queue/useResearchQueue";
import { useCreateShadowPortfolio, useResearchRun, useResearchRuns, useRunBacktest } from "./hooks";
import { backtestResult } from "./model";
import { PerformanceChart } from "./PerformanceChart";

const CAP_OPTIONS: readonly SelectOption<string>[] = [
  { value: "all", label: "All capitalization tiers" },
  ...researchDeployment.capTiers.map((tier) => ({ value: tier, label: `${tier.charAt(0).toUpperCase()}${tier.slice(1)} cap` })),
];

function value(value: number | null, suffix = ""): string {
  return value === null ? "—" : `${value.toFixed(2)}${suffix}`;
}

export function HypothesisLabPage() {
  const workspaces = useResearchWorkspaces();
  const workspace = workspaces.data?.[0];
  const runs = useResearchRuns(workspace?.id);
  const latestSummary = runs.data?.find((run) => run.runKind === "hypothesis");
  const latest = useResearchRun(workspace?.id, latestSummary?.id);
  const runBacktest = useRunBacktest(workspace?.id);
  const createShadow = useCreateShadowPortfolio(workspace?.id);
  const activeRun = runBacktest.data ?? latest.data;
  const result = useMemo(() => backtestResult(activeRun), [activeRun]);
  const [capTier, setCapTier] = useState("all");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [universeLimit, setUniverseLimit] = useState(25);
  const [capital, setCapital] = useState(100_000);
  const [bookName, setBookName] = useState(`${researchDeployment.market} systematic shadow`);
  const strategyKey = researchDeployment.market === "DSE" ? "dse_reversal_v1" : "us_breakout_v1";

  const submit = () => runBacktest.mutate({
    strategy_key: strategyKey,
    ...(startDate ? { start_date: startDate } : {}),
    ...(endDate ? { end_date: endDate } : {}),
    ...(capTier !== "all" ? { cap_tier: capTier } : {}),
    universe_limit: universeLimit,
    initial_capital: capital,
  });

  return (
    <div className="atlas-page">
      <header className="atlas-page-header">
        <div><span className="atlas-page-header__eyebrow">Registered experiments · no discretionary override</span><h1>Hypothesis lab</h1><p>No-lookahead signal replay, next-session execution, transaction costs, deterministic risk, and explicit current-universe limitations.</p></div>
        <StatusBadge tone="info" dot>{strategyKey}</StatusBadge>
      </header>

      <div className="lab-layout">
        <aside className="atlas-panel lab-config">
          <header><FlaskConical aria-hidden="true" size={16} /><span><strong>Experiment specification</strong><small>Inputs are stored with the run</small></span></header>
          <label>Registered strategy<input disabled value={strategyKey} /></label>
          <label>Capitalization mandate<SelectField label="Capitalization mandate" onChange={setCapTier} options={CAP_OPTIONS} value={capTier} /></label>
          <span className="lab-config__split">
            <label>Start date<input onChange={(event) => setStartDate(event.target.value)} type="date" value={startDate} /></label>
            <label>End date<input onChange={(event) => setEndDate(event.target.value)} type="date" value={endDate} /></label>
          </span>
          <label>Universe limit<input max="30" min="5" onChange={(event) => setUniverseLimit(Number(event.target.value))} type="number" value={universeLimit} /></label>
          <label>Initial capital ({researchDeployment.currency})<input min="1" onChange={(event) => setCapital(Number(event.target.value))} type="number" value={capital} /></label>
          <Button isDisabled={!workspace || runBacktest.isPending} onPress={submit} variant="primary"><Play aria-hidden="true" size={14} />{runBacktest.isPending ? "Running portfolio simulation…" : "Run registered backtest"}</Button>
          {runBacktest.isError && <p className="atlas-error"><AlertTriangle size={13} />{runBacktest.error.message}</p>}
          <p className="lab-config__policy">The engine is long-only. Signals use completed data through T; fills cannot occur before the next observable open.</p>
        </aside>

        <main className="lab-results">
          {!result ? (
            <section className="atlas-empty"><TestTube2 aria-hidden="true" size={28} /><h2>No completed experiment</h2><p>Run the market-bound registered strategy. Atlas will retain every input, result, failure gate, and evidence fingerprint.</p></section>
          ) : (
            <>
              <section className="atlas-panel result-overview">
                <header><span><strong>{result.strategy.name}</strong><small>{result.startDate ?? "No first session"} to {result.endDate ?? "No last session"}</small></span><StatusBadge tone={result.validationStatus === "eligible_for_shadow" ? "positive" : "warning"} dot>{result.validationStatus === "eligible_for_shadow" ? "Shadow eligible" : "Diagnostic only"}</StatusBadge></header>
                <div className="atlas-kpis">
                  <span><small>Ending NAV</small><strong>{result.finalNav.toLocaleString()}</strong></span>
                  <span><small>Benchmark</small><strong>{result.benchmarkFinal.toLocaleString()}</strong></span>
                  <span><small>Executions</small><strong>{result.trades.length}</strong></span>
                  <span><small>Turnover</small><strong>{result.turnoverPct.toFixed(1)}%</strong></span>
                  <span><small>Explicit fees</small><strong>{result.feesPaid.toLocaleString()}</strong></span>
                </div>
                <PerformanceChart points={result.equityCurve} />
              </section>

              <section className="atlas-panel">
                <header><ShieldCheck aria-hidden="true" size={16} /><span><strong>Validation and risk report</strong><small>Train, validation, and untouched terminal split remain separate</small></span></header>
                <div className="metric-table" role="table">
                  <div role="row"><span>Slice</span><span>Sessions</span><span>Total return</span><span>Ann. return</span><span>Sharpe</span><span>Max drawdown</span></div>
                  {result.metrics.map((metric) => <div key={metric.label} role="row"><strong>{metric.label}</strong><span>{metric.sessions}</span><span className={(metric.totalReturnPct ?? 0) >= 0 ? "value-up" : "value-down"}>{value(metric.totalReturnPct, "%")}</span><span>{value(metric.annualizedReturnPct, "%")}</span><span>{value(metric.sharpe)}</span><span>{value(metric.maxDrawdownPct, "%")}</span></div>)}
                </div>
                {result.failedGates.length > 0 && <div className="validation-gates"><strong>Why this is not validated</strong>{result.failedGates.map((gate) => <span key={gate}><AlertTriangle size={12} />{gate}</span>)}</div>}
              </section>

              <section className="atlas-panel shadow-launch">
                <header><WalletCards aria-hidden="true" size={16} /><span><strong>Forward shadow evaluation</strong><small>No broker connection and no capital at risk</small></span></header>
                <div><label>Book name<input onChange={(event) => setBookName(event.target.value)} value={bookName} /></label><Button isDisabled={!activeRun || bookName.trim().length < 3 || createShadow.isPending} onPress={() => activeRun && createShadow.mutate({ sourceRunId: activeRun.id, name: bookName.trim() })} variant="primary">Start shadow book</Button></div>
                {createShadow.isSuccess && <p className="atlas-success">Shadow book created. It will advance only over newly completed market sessions.</p>}
                {createShadow.isError && <p className="atlas-error"><AlertTriangle size={13} />{createShadow.error.message}</p>}
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
