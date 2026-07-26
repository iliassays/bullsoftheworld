import { AlertTriangle, FileLock2, FlaskConical, Play, ShieldCheck, TestTube2, WalletCards } from "lucide-react";
import { useMemo, useState } from "react";

import { researchDeployment } from "../../app/deployment";
import type { BacktestStrategyKey } from "../../app/api-client";
import { Button, SelectField, StatusBadge, type SelectOption } from "../../design-system";
import { useResearchWorkspaces } from "../research-queue/useResearchQueue";
import { useCreateShadowPortfolio, useInvestmentOperatingView, useResearchRun, useResearchRuns, useRunBacktest } from "./hooks";
import { backtestResult } from "./model";
import { PerformanceChart } from "./PerformanceChart";

const CAP_OPTIONS: readonly SelectOption<string>[] = [
  { value: "all", label: "All capitalization tiers" },
  ...researchDeployment.capTiers.map((tier) => ({ value: tier, label: `${tier.charAt(0).toUpperCase()}${tier.slice(1)} cap` })),
];

const US_STRATEGIES: readonly SelectOption<BacktestStrategyKey>[] = [
  { value: "us_activist_13d_v1", label: "A1 · Activist 13D event book" },
  { value: "us_insider_cluster_v1", label: "A2 · Insider cluster event book" },
  { value: "us_forced_seller_v1", label: "B · Forced-seller event book (data gated)" },
  { value: "us_factor_sleeve_v1", label: "C · Factor sleeve" },
  { value: "us_breakout_v1", label: "Legacy · Liquid trend participation" },
];

const DSE_STRATEGIES: readonly SelectOption<BacktestStrategyKey>[] = [
  { value: "dse_compression_breakout_20d_v1", label: "DSE compression breakout · locked 20-session study" },
  { value: "dse_selective_compression_v1", label: "DSE selective compression · three-position candidate" },
  { value: "dse_reversal_v1", label: "DSE liquid reversal" },
];

function value(value: number | null, suffix = ""): string {
  return value === null ? "—" : `${value.toFixed(2)}${suffix}`;
}

export function HypothesisLabPage() {
  const workspaces = useResearchWorkspaces();
  const workspace = workspaces.data?.[0];
  const runs = useResearchRuns(workspace?.id);
  const operating = useInvestmentOperatingView(workspace?.id);
  const latestSummary = runs.data?.find((run) => run.runKind === "hypothesis");
  const latest = useResearchRun(workspace?.id, latestSummary?.id);
  const runBacktest = useRunBacktest(workspace?.id);
  const createShadow = useCreateShadowPortfolio(workspace?.id);
  const activeRun = runBacktest.data ?? latest.data;
  const result = useMemo(() => backtestResult(activeRun), [activeRun]);
  const trial = useMemo(
    () => operating.data?.trials.find((item) => item.sourceRunId === activeRun?.id),
    [activeRun?.id, operating.data?.trials],
  );
  const [capTier, setCapTier] = useState("all");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [universeLimit, setUniverseLimit] = useState(25);
  const [capital, setCapital] = useState(100_000);
  const [bookName, setBookName] = useState(`${researchDeployment.market} systematic shadow`);
  const strategyOptions = researchDeployment.market === "DSE" ? DSE_STRATEGIES : US_STRATEGIES;
  const [strategyKey, setStrategyKey] = useState<BacktestStrategyKey>(
    researchDeployment.market === "DSE" ? "dse_reversal_v1" : "us_activist_13d_v1",
  );
  const institutionalExecution = strategyKey.startsWith("us_") && strategyKey !== "us_breakout_v1";
  const broadCompressionRejected = result?.strategy.key === "dse_compression_breakout_20d_v1";
  const selectiveCompression = result?.strategy.key === "dse_selective_compression_v1";
  const strategyAdmissionAllowsShadow = !broadCompressionRejected && (
    !selectiveCompression || result?.forwardObservationAdmission?.passed === true
  );
  const shadowable = Boolean(
    activeRun &&
    result?.endDate &&
    result.equityCurve.length > 0 &&
    result.systemReadiness.status !== "data_blocked" &&
    strategyAdmissionAllowsShadow,
  );

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
          <label>Registered strategy<SelectField label="Registered strategy" onChange={(key) => {
            const selected = key as BacktestStrategyKey;
            setStrategyKey(selected);
            if (
              selected === "dse_compression_breakout_20d_v1" ||
              selected === "dse_selective_compression_v1"
            ) setUniverseLimit(500);
          }} options={strategyOptions} value={strategyKey} /></label>
          <label>Capitalization mandate<SelectField label="Capitalization mandate" onChange={setCapTier} options={CAP_OPTIONS} value={capTier} /></label>
          <span className="lab-config__split">
            <label>Start date<input onChange={(event) => setStartDate(event.target.value)} type="date" value={startDate} /></label>
            <label>End date<input onChange={(event) => setEndDate(event.target.value)} type="date" value={endDate} /></label>
          </span>
          <label>Universe limit<input max="500" min="5" onChange={(event) => setUniverseLimit(Number(event.target.value))} type="number" value={universeLimit} /></label>
          <label>Initial capital ({researchDeployment.currency})<input min="1" onChange={(event) => setCapital(Number(event.target.value))} type="number" value={capital} /></label>
          <Button isDisabled={!workspace || runBacktest.isPending} onPress={submit} variant="primary"><Play aria-hidden="true" size={14} />{runBacktest.isPending ? "Running portfolio simulation…" : "Run registered backtest"}</Button>
          {runBacktest.isError && <p className="atlas-error"><AlertTriangle size={13} />{runBacktest.error.message}</p>}
          <p className="lab-config__policy">The engine is long-only. Signals use completed data through T; fills cannot occur before the next observable {institutionalExecution ? "close" : "open"}.</p>
        </aside>

        <main className="lab-results">
          {!result ? (
            <section className="atlas-empty"><TestTube2 aria-hidden="true" size={28} /><h2>No completed experiment</h2><p>Run the market-bound registered strategy. Atlas will retain every input, result, failure gate, and evidence fingerprint.</p></section>
          ) : (
            <>
              <section className="atlas-panel trial-registration">
                <header>
                  <FileLock2 aria-hidden="true" size={16} />
                  <span><strong>Trial registration</strong><small>Frozen before simulation; failures remain in the registry</small></span>
                  <StatusBadge tone={trial?.registrationState === "preregistered" ? "positive" : "warning"}>{trial?.registrationState === "preregistered" ? "Preregistered" : "Legacy reconstructed"}</StatusBadge>
                </header>
                {trial ? (
                  <div>
                    <span><small>Economic mechanism</small><strong>{trial.economicHypothesis}</strong></span>
                    <span><small>Method version</small><strong>{trial.strategyVersion}</strong></span>
                    <span><small>Specification hash</small><strong title={trial.specificationHash}>{trial.specificationHash.slice(0, 14)}…</strong></span>
                    <span><small>Registry state</small><strong>{trial.status} · family attempt {trial.trialSequence}</strong></span>
                  </div>
                ) : (
                  <p className="portfolio-data-note">This result predates the strategy-trial registry. It cannot be represented as preregistered.</p>
                )}
              </section>

              <section className="atlas-panel result-overview">
                <header><span><strong>{result.strategy.name}</strong><small>{result.startDate ?? "No first session"} to {result.endDate ?? "No last session"}</small></span><StatusBadge tone={result.validationStatus === "eligible_for_shadow" ? "positive" : "warning"} dot>{result.validationStatus === "eligible_for_shadow" ? "Shadow eligible" : "Diagnostic only"}</StatusBadge></header>
                <div className={`system-state system-state--${result.systemReadiness.status}`}>
                  <strong>System state · {result.systemReadiness.status.replace(/_/g, " ")}</strong>
                  <span>{result.systemReadiness.statement}</span>
                  <span>Execution clock: {result.systemReadiness.executionTiming.replace("_", " ")}</span>
                  {result.systemReadiness.missingDatasets.map((dataset) => <span key={dataset}><AlertTriangle size={12} />{dataset}</span>)}
                </div>
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
                <div className="cost-stress">
                  <strong>Named-regime evidence</strong>
                  <p className="guard-lede">Atlas reports each required market environment separately. A missing period is a validation failure, not a zero return.</p>
                  {result.robustnessSlices.length > 0 ? <div className="metric-table" role="table">
                    <div role="row"><span>Regime</span><span>Sessions</span><span>Return</span><span>Benchmark</span><span>Excess</span><span>Max drawdown</span></div>
                    {result.robustnessSlices.map((slice) => <div key={slice.key} role="row">
                      <strong title={`${slice.startDate} to ${slice.endDate}`}>{slice.label}</strong>
                      <span>{slice.sessions}</span>
                      <span className={slice.totalReturnPct >= 0 ? "value-up" : "value-down"}>{value(slice.totalReturnPct, "%")}</span>
                      <span>{value(slice.benchmarkReturnPct, "%")}</span>
                      <span className={slice.excessReturnPct >= 0 ? "value-up" : "value-down"}>{value(slice.excessReturnPct, "%")}</span>
                      <span>{value(slice.maxDrawdownPct, "%")}</span>
                    </div>)}
                  </div> : <p className="guard-note">No named stress window has enough observations to report.</p>}
                </div>
                {result.deflatedSharpe && <div className="overfitting-guard">
                  <strong>Overfitting guard</strong>
                  <p className="guard-lede">A backtest picked as the best of many attempts flatters itself. This discounts the result by how many variants were tried.</p>
                  <div className="guard-grid">
                    <span><small>Confidence the edge is real</small><b className={result.deflatedSharpe.passes ? "value-up" : "value-down"}>{(result.deflatedSharpe.deflatedSharpe * 100).toFixed(1)}%</b></span>
                    <span><small>Before adjusting for attempts</small><b>{(result.deflatedSharpe.probabilisticSharpe * 100).toFixed(1)}%</b></span>
                    <span><small>Variants tried</small><b>{result.deflatedSharpe.numTrials}</b></span>
                    <span><small>Bar to clear</small><b>{(result.deflatedSharpe.threshold * 100).toFixed(0)}%</b></span>
                  </div>
                  <p className="guard-note">{result.deflatedSharpe.passes
                    ? "Clears the bar: the result is unlikely to be an artefact of repeated searching."
                    : "Does not clear the bar. Treat this as a diagnostic, not evidence of an edge."}</p>
                </div>}
                {result.costStress && <div className="cost-stress">
                  <strong>Where the edge dies</strong>
                  <p className="guard-lede">Re-run at rising trading costs. Spread measured per name on {result.costStress.measuredCoverage} of {result.costStress.universeSize} securities, never assumed.</p>
                  <div className="metric-table" role="table">
                    <div role="row"><span>Cost assumption</span><span>One-way</span><span>Net return</span><span>vs benchmark</span><span>Edge</span></div>
                    {result.costStress.tiers.map((tier) => <div key={tier.label} role="row">
                      <strong>{tier.measured ? "Measured" : `Stress ${tier.oneWayBps}bps`}</strong>
                      <span>{tier.oneWayBps.toFixed(1)}bps</span>
                      <span className={tier.netReturnPct >= 0 ? "value-up" : "value-down"}>{value(tier.netReturnPct, "%")}</span>
                      <span className={tier.excessReturnPct >= 0 ? "value-up" : "value-down"}>{value(tier.excessReturnPct, "%")}</span>
                      <span>{tier.edgeSurvives ? "survives" : "gone"}</span>
                    </div>)}
                  </div>
                  <p className="guard-note">{result.costStress.edgeDiesAtBps !== null
                    ? `The edge stops beating its benchmark at ${result.costStress.edgeDiesAtBps}bps one-way. Anything that dies by 30bps is not tradeable at retail cost.`
                    : "The edge survives every stress tier tested, including 50bps one-way."}</p>
                </div>}
                {result.nullModels.length > 0 && <div className="cost-stress">
                  <strong>Null-model challenge</strong>
                  <p className="guard-lede">The active construction must beat simpler portfolios using the same observable universe and execution clock.</p>
                  <div className="metric-table" role="table">
                    <div role="row"><span>Comparator</span><span>Realistic return</span><span>30 bps return</span><span>Verdict</span></div>
                    {result.nullModels.map((model) => {
                      const passed = model.strategyBeatsRealistic && model.strategyBeatsStress30Bps;
                      return <div key={model.key} role="row">
                        <strong>{model.key.replace(/_/g, " ")}</strong>
                        <span>{value(model.realisticReturnPct, "%")}</span>
                        <span>{value(model.stress30BpsReturnPct, "%")}</span>
                        <span className={passed ? "value-up" : "value-down"}>{passed ? "beaten" : "not beaten"}</span>
                      </div>;
                    })}
                  </div>
                </div>}
                {result.forwardObservationAdmission && <div className="cost-stress">
                  <strong>Selective forward-book admission</strong>
                  <p className="guard-lede">This is the decision that controls whether Atlas may open a diagnostic paper book. Scanner membership alone never qualifies.</p>
                  <div className="metric-table" role="table">
                    <div role="row"><span>Window</span><span>Sessions</span><span>Net return</span><span>Benchmark</span><span>Excess</span></div>
                    {result.forwardObservationAdmission.chronologicalSlices.map((slice) => <div key={slice.label} role="row">
                      <strong>{slice.label}</strong>
                      <span>{slice.sessions}</span>
                      <span className={(slice.netReturnPct ?? 0) > 0 ? "value-up" : "value-down"}>{value(slice.netReturnPct, "%")}</span>
                      <span>{value(slice.benchmarkReturnPct, "%")}</span>
                      <span className={(slice.excessReturnPct ?? 0) > 0 ? "value-up" : "value-down"}>{value(slice.excessReturnPct, "%")}</span>
                    </div>)}
                  </div>
                  <p className="guard-note">
                    {result.forwardObservationAdmission.passed
                      ? `Admitted for diagnostic forward observation: ${result.forwardObservationAdmission.acceptedEntries} qualified entries, ${result.forwardObservationAdmission.buyExecutions} executed entries. This is not promotion.`
                      : `Not admitted. No paper book will be created. Failed: ${result.forwardObservationAdmission.failedChecks.map((check) => check.replace(/_/g, " ")).join("; ")}.`}
                  </p>
                </div>}
                {result.failedGates.length > 0 && <div className="validation-gates"><strong>Why this is not validated</strong>{result.failedGates.map((gate) => <span key={gate}><AlertTriangle size={12} />{gate}</span>)}</div>}
              </section>

              <section className="atlas-panel shadow-launch">
                <header><WalletCards aria-hidden="true" size={16} /><span><strong>Forward shadow evaluation</strong><small>No broker connection and no capital at risk</small></span></header>
                <div><label>Book name<input onChange={(event) => setBookName(event.target.value)} value={bookName} /></label><Button isDisabled={!shadowable || bookName.trim().length < 3 || createShadow.isPending} onPress={() => activeRun && createShadow.mutate({ sourceRunId: activeRun.id, name: bookName.trim() })} variant="primary">Start shadow book</Button></div>
                {!shadowable && <p className="portfolio-data-note">{broadCompressionRejected
                  ? "The broad compression strategy failed its historical diagnostic and is paused. It cannot start another book."
                  : selectiveCompression && result.forwardObservationAdmission?.passed !== true
                    ? "The selective strategy has not passed its fixed admission gate. Atlas will not create a paper book."
                    : "A shadow book requires at least one completed market session and a system that is not data-blocked."}</p>}
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
