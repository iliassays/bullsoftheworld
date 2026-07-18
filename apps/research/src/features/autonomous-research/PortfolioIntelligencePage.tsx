import {
  Activity,
  AlertTriangle,
  BriefcaseBusiness,
  GitBranch,
  Landmark,
  ListChecks,
  RefreshCw,
  ScanSearch,
  Settings2,
  ShieldAlert,
} from "lucide-react";
import { useMemo, useState } from "react";

import { researchDeployment } from "../../app/deployment";
import type { InvestmentMandate } from "../../app/api-client";
import { Button, SelectField, StatusBadge } from "../../design-system";
import { useResearchWorkspaces } from "../research-queue/useResearchQueue";
import { useConfigureInvestmentMandate, useInvestmentOperatingView, useShadowPortfolios } from "./hooks";
import { shadowExecutions } from "./model";
import { PerformanceChart } from "./PerformanceChart";
import { strategySelectionGuide } from "./strategy-guide";

function currency(value: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: researchDeployment.currency, maximumFractionDigits: 0 }).format(value);
}

function executionCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: researchDeployment.currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function executionDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function detail(value: unknown): string {
  return typeof value === "string" ? value : "Risk policy intervened.";
}

function optionalNumber(value: unknown, digits: number, suffix = ""): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toFixed(digits)}${suffix}`
    : "Unavailable";
}

function object(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function MandateEditor({
  mandate,
  workspaceId,
  onClose,
}: {
  mandate: InvestmentMandate;
  workspaceId: string;
  onClose: () => void;
}) {
  const configure = useConfigureInvestmentMandate(workspaceId);
  const [objective, setObjective] = useState(mandate.objective);
  const [limits, setLimits] = useState({
    maxGrossExposurePct: mandate.maxGrossExposurePct,
    minCashReservePct: mandate.minCashReservePct,
    maxPositionWeightPct: mandate.maxPositionWeightPct,
    maxSectorWeightPct: mandate.maxSectorWeightPct,
    maxAdvParticipationPct: mandate.maxAdvParticipationPct,
    portfolioDrawdownBrakePct: mandate.portfolioDrawdownBrakePct,
    stressLossLimitPct: mandate.stressLossLimitPct,
  });
  const setLimit = (key: keyof typeof limits, value: string) => {
    setLimits((current) => ({ ...current, [key]: Number(value) }));
  };
  const valid = objective.trim().length >= 20 && Object.values(limits).every(Number.isFinite);
  const save = () => configure.mutate(
    {
      objective: objective.trim(),
      benchmark_key: mandate.benchmarkKey,
      max_gross_exposure_pct: limits.maxGrossExposurePct,
      min_cash_reserve_pct: limits.minCashReservePct,
      max_position_weight_pct: limits.maxPositionWeightPct,
      max_sector_weight_pct: limits.maxSectorWeightPct,
      max_adv_participation_pct: limits.maxAdvParticipationPct,
      portfolio_drawdown_brake_pct: limits.portfolioDrawdownBrakePct,
      stress_loss_limit_pct: limits.stressLossLimitPct,
    },
    { onSuccess: onClose },
  );

  return (
    <section aria-label="Create a new investment mandate version" className="mandate-editor">
      <header><strong>New mandate version</strong><small>Existing books keep their pinned limits. New trials and books use this version.</small></header>
      <label>Portfolio objective<textarea onChange={(event) => setObjective(event.target.value)} rows={3} value={objective} /></label>
      <div>
        <label>Gross ceiling %<input max="100" min="1" onChange={(event) => setLimit("maxGrossExposurePct", event.target.value)} step="0.1" type="number" value={limits.maxGrossExposurePct} /></label>
        <label>Cash reserve %<input max="99" min="0" onChange={(event) => setLimit("minCashReservePct", event.target.value)} step="0.1" type="number" value={limits.minCashReservePct} /></label>
        <label>Single name %<input max="100" min="0.1" onChange={(event) => setLimit("maxPositionWeightPct", event.target.value)} step="0.1" type="number" value={limits.maxPositionWeightPct} /></label>
        <label>Sector ceiling %<input max="100" min="0.1" onChange={(event) => setLimit("maxSectorWeightPct", event.target.value)} step="0.1" type="number" value={limits.maxSectorWeightPct} /></label>
        <label>ADV participation %<input max="100" min="0.1" onChange={(event) => setLimit("maxAdvParticipationPct", event.target.value)} step="0.1" type="number" value={limits.maxAdvParticipationPct} /></label>
        <label>Drawdown brake %<input max="100" min="0.1" onChange={(event) => setLimit("portfolioDrawdownBrakePct", event.target.value)} step="0.1" type="number" value={limits.portfolioDrawdownBrakePct} /></label>
        <label>Stress loss limit %<input max="100" min="0.1" onChange={(event) => setLimit("stressLossLimitPct", event.target.value)} step="0.1" type="number" value={limits.stressLossLimitPct} /></label>
      </div>
      {configure.isError && <p className="atlas-error"><AlertTriangle size={13} />{configure.error.message}</p>}
      <footer><Button onPress={onClose} variant="quiet">Cancel</Button><Button isDisabled={!valid || configure.isPending} onPress={save} variant="primary">{configure.isPending ? "Creating version…" : "Create mandate version"}</Button></footer>
    </section>
  );
}

export function PortfolioIntelligencePage() {
  const workspace = useResearchWorkspaces().data?.[0];
  const portfolios = useShadowPortfolios(workspace?.id);
  const operating = useInvestmentOperatingView(workspace?.id);
  const [selectedId, setSelectedId] = useState("");
  const [editingMandate, setEditingMandate] = useState(false);
  const selected = useMemo(() => portfolios.data?.find((item) => item.id === selectedId) ?? portfolios.data?.[0], [portfolios.data, selectedId]);
  const selectedAnalytics = useMemo(
    () => operating.data?.portfolios.find((item) => item.portfolioId === selected?.id),
    [operating.data?.portfolios, selected?.id],
  );
  const executions = useMemo(() => shadowExecutions(selected), [selected]);
  const latest = selected?.snapshots.at(-1);
  const positionPlan = useMemo(() => {
    if (!latest) return [];
    return [...new Set([...Object.keys(latest.positions), ...Object.keys(latest.targetWeights)])]
      .sort((left, right) => (latest.targetWeights[right] ?? 0) - (latest.targetWeights[left] ?? 0) || left.localeCompare(right))
      .map((code) => {
        const position = latest.positions[code];
        const target = latest.targetWeights[code] ?? 0;
        return {
          code,
          shares: position?.shares ?? 0,
          averageCost: position?.average_cost ?? null,
          target,
          state: position && target > 0 ? "Held / rebalance" : position ? "Exit queued" : "Entry queued",
          stateKey: position && target > 0 ? "held" : position ? "exit" : "entry",
        };
      });
  }, [latest]);
  const totalReturn = latest && selected && selected.initialCapital > 0 ? (latest.nav / selected.initialCapital - 1) * 100 : 0;
  const benchmarkReturn = latest && selected && selected.initialCapital > 0 ? (latest.benchmarkNav / selected.initialCapital - 1) * 100 : 0;
  const promotion = object(selected?.configuration.promotion);
  const promotionStatus = typeof promotion?.status === "string" ? promotion.status : "not evaluated";
  const promotionChecks = Array.isArray(promotion?.checks)
    ? promotion.checks.flatMap((value) => {
        const check = object(value);
        return check && typeof check.key === "string" && typeof check.passed === "boolean" ? [check] : [];
      })
    : [];
  const observableUniverse = Array.isArray(selected?.configuration.observable_universe)
    ? selected.configuration.observable_universe.filter((value): value is string => typeof value === "string")
    : null;
  const selectionGuide = selected
    ? strategySelectionGuide(selected.strategyKey, observableUniverse?.length ?? null)
    : null;

  if (portfolios.isLoading || operating.isLoading) return <div aria-label="Loading shadow portfolios" className="research-loading"><span className="research-loading__body" /></div>;
  if (portfolios.isError || operating.isError) return <section className="research-unavailable"><AlertTriangle size={26} /><h1>Portfolio intelligence unavailable</h1><p>{portfolios.error?.message ?? operating.error?.message}</p><Button onPress={() => { void portfolios.refetch(); void operating.refetch(); }}><RefreshCw size={14} />Retry</Button></section>;

  return (
    <div className="atlas-page">
      <header className="atlas-page-header">
        <div><span className="atlas-page-header__eyebrow">Forward-only strategy experiment · deterministic risk authority</span><h1>Portfolio intelligence</h1><p>This systematic paper book is independent from company-research verdicts. Observe implementation costs, concentration, drawdown, and every risk intervention.</p></div>
        {selected && <SelectField label="Shadow book" onChange={setSelectedId} options={(portfolios.data ?? []).map((item) => ({ value: item.id, label: item.name }))} value={selected.id} />}
      </header>

      {!selected || !latest ? (
        <section className="atlas-empty"><BriefcaseBusiness size={28} /><h2>No active shadow book</h2><p>Complete a hypothesis backtest and start forward evaluation from the Hypothesis lab.</p></section>
      ) : (
        <>
          {selectionGuide && (
            <section className="atlas-panel strategy-selection-guide">
              <header><ScanSearch size={16} /><span><strong>How a security enters this paper book</strong><small>Independent from the Research queue and its urgency score</small></span></header>
              <div>
                <span><small>1 · Universe</small><strong>{selectionGuide.universe}</strong></span>
                <span><small>2 · Entry gates</small><strong>{selectionGuide.entry}</strong></span>
                <span><small>3 · Ranking</small><strong>{selectionGuide.ranking}</strong></span>
                <span><small>4 · Position size</small><strong>{selectionGuide.sizing}</strong></span>
              </div>
            </section>
          )}
          <section className="atlas-panel portfolio-command">
            <header><span><strong>{selected.name}</strong><small>{selected.strategyKey} · inception {selected.inceptionDate}</small></span><StatusBadge tone={selected.status === "active" ? "positive" : "negative"} dot>{selected.status}</StatusBadge></header>
            {typeof selected.configuration.refresh_error === "string" && <div className="portfolio-stop"><ShieldAlert size={14} /><span><strong>Advancement stopped safely</strong>{selected.configuration.refresh_error}</span></div>}
            <div className="promotion-gate"><span><small>Promotion gate</small><strong>{typeof promotion?.headline === "string" ? promotion.headline : "Awaiting the first forward evaluation."}</strong></span><StatusBadge tone={promotionStatus === "eligible" ? "positive" : promotionStatus === "rejected" ? "negative" : "warning"}>{promotionStatus}</StatusBadge>{promotionChecks.length > 0 && <div>{promotionChecks.map((check) => <span className={check.passed ? "promotion-check--passed" : "promotion-check--failed"} key={String(check.key)}>{check.passed ? "Pass" : "Blocked"} · {String(check.key).replace(/_/g, " ")}</span>)}</div>}</div>
            <div className="atlas-kpis">
              <span><small>NAV</small><strong>{currency(latest.nav)}</strong></span>
              <span><small>Net return</small><strong className={totalReturn >= 0 ? "value-up" : "value-down"}>{totalReturn.toFixed(2)}%</strong></span>
              <span><small>Benchmark return</small><strong>{benchmarkReturn.toFixed(2)}%</strong></span>
              <span><small>Gross exposure</small><strong>{latest.grossExposurePct.toFixed(1)}%</strong></span>
              <span><small>Current drawdown</small><strong className={latest.drawdownPct > 10 ? "value-down" : ""}>{latest.drawdownPct.toFixed(2)}%</strong></span>
              <span><small>Cumulative fees</small><strong>{currency(latest.cumulativeFees)}</strong></span>
            </div>
            <PerformanceChart points={selected.snapshots.map((snapshot) => ({ date: snapshot.asOfDate, nav: snapshot.nav, benchmark: snapshot.benchmarkNav }))} />
          </section>

          {operating.data?.mandate && selectedAnalytics && (
            <section className="atlas-panel mandate-control">
              <header>
                <Landmark aria-hidden="true" size={16} />
                <span><strong>Investment mandate</strong><small>Version {selectedAnalytics.mandateVersion} · {selectedAnalytics.mandateBinding === "pinned" ? "pinned at book inception" : "legacy book evaluated against the active mandate"}</small></span>
                <StatusBadge tone={selectedAnalytics.risk.breachedLimits.length ? "negative" : selectedAnalytics.risk.dataComplete ? "positive" : "warning"}>{selectedAnalytics.risk.breachedLimits.length ? `${selectedAnalytics.risk.breachedLimits.length} breached` : selectedAnalytics.risk.dataComplete ? "Within observed limits" : "Risk data incomplete"}</StatusBadge>
                <Button onPress={() => setEditingMandate((value) => !value)} variant="quiet"><Settings2 aria-hidden="true" size={13} />{editingMandate ? "Close" : "Edit"}</Button>
              </header>
              <p>{selectedAnalytics.mandate.objective}</p>
              {operating.data.mandate.version !== selectedAnalytics.mandate.version && (
                <p className="portfolio-data-note">Workspace mandate v{operating.data.mandate.version} is active for future trials and books. This book remains governed by its pinned v{selectedAnalytics.mandate.version} limits.</p>
              )}
              <div>
                <span><small>Benchmark</small><strong>{selectedAnalytics.mandate.benchmarkKey.replace(/_/g, " ")}</strong></span>
                <span><small>Gross ceiling</small><strong>{selectedAnalytics.mandate.maxGrossExposurePct.toFixed(0)}%</strong></span>
                <span><small>Single name</small><strong>{selectedAnalytics.mandate.maxPositionWeightPct.toFixed(0)}%</strong></span>
                <span><small>Sector ceiling</small><strong>{selectedAnalytics.mandate.maxSectorWeightPct.toFixed(0)}%</strong></span>
                <span><small>ADV participation</small><strong>{selectedAnalytics.mandate.maxAdvParticipationPct.toFixed(1)}%</strong></span>
                <span><small>Drawdown brake</small><strong>{selectedAnalytics.mandate.portfolioDrawdownBrakePct.toFixed(0)}%</strong></span>
              </div>
              {editingMandate && <MandateEditor mandate={operating.data.mandate} onClose={() => setEditingMandate(false)} workspaceId={workspace!.id} />}
            </section>
          )}

          {selectedAnalytics && (
            <div className="portfolio-analytics-grid">
              <section className="atlas-panel portfolio-risk-report">
                <header><ShieldAlert aria-hidden="true" size={16} /><span><strong>Risk and capacity</strong><small>Point-in-time positions against the pinned mandate</small></span></header>
                <div className="portfolio-risk-kpis">
                  <span><small>Largest position</small><strong>{selectedAnalytics.risk.largestPositionPct.toFixed(1)}%</strong><em>limit {selectedAnalytics.mandate.maxPositionWeightPct.toFixed(0)}%</em></span>
                  <span><small>Largest sector</small><strong>{selectedAnalytics.risk.largestSectorPct.toFixed(1)}%</strong><em>limit {selectedAnalytics.mandate.maxSectorWeightPct.toFixed(0)}%</em></span>
                  <span><small>Effective positions</small><strong>{selectedAnalytics.risk.effectivePositions.toFixed(1)}</strong><em>concentration-adjusted</em></span>
                  <span><small>Max exit time</small><strong>{optionalNumber(selectedAnalytics.risk.maximumExitDays, 1, " days")}</strong><em>at mandate ADV</em></span>
                  <span><small>Weighted correlation</small><strong>{optionalNumber(selectedAnalytics.risk.weightedAverageCorrelation, 2)}</strong><em>60-session maximum</em></span>
                </div>
                <div className="stress-list">
                  {selectedAnalytics.risk.stressScenarios.map((scenario) => (
                    <article key={scenario.key}>
                      <span><strong>{scenario.label}</strong><small>{scenario.methodology}</small></span>
                      <span className={scenario.status === "breached" ? "value-down" : ""}>{optionalNumber(scenario.estimatedLossPct, 2, "% NAV loss")}</span>
                    </article>
                  ))}
                </div>
                {selectedAnalytics.risk.dataQualityNotes.map((note) => <p className="portfolio-data-note" key={note}>{note}</p>)}
              </section>

              <section className="atlas-panel performance-attribution">
                <header><Activity aria-hidden="true" size={16} /><span><strong>Performance attribution</strong><small>What is measured, proxied, or still unavailable</small></span></header>
                <div className="attribution-summary">
                  <span><small>Portfolio</small><strong>{selectedAnalytics.attribution.portfolioReturnPct.toFixed(2)}%</strong></span>
                  <span><small>Benchmark</small><strong>{selectedAnalytics.attribution.benchmarkReturnPct.toFixed(2)}%</strong></span>
                  <span><small>Excess</small><strong className={selectedAnalytics.attribution.excessReturnPct >= 0 ? "value-up" : "value-down"}>{selectedAnalytics.attribution.excessReturnPct.toFixed(2)}%</strong></span>
                </div>
                <div className="attribution-components">
                  {selectedAnalytics.attribution.components.map((component) => (
                    <article key={component.key}>
                      <span><strong>{component.label}</strong><small>{component.explanation}</small></span>
                      <span><StatusBadge tone={component.quality === "exact" ? "positive" : component.quality === "proxy" ? "warning" : "neutral"}>{component.quality}</StatusBadge><strong>{component.contributionPct == null ? "—" : `${component.contributionPct >= 0 ? "+" : ""}${optionalNumber(component.contributionPct, 2, "%")}`}</strong></span>
                    </article>
                  ))}
                </div>
              </section>
            </div>
          )}

          <div className="portfolio-grid">
            <section className="atlas-panel">
              <header><Activity size={16} /><span><strong>Positions and next-session targets</strong><small>Targets formed after {latest.asOfDate} close · execution remains risk-gated</small></span></header>
              <div className="portfolio-table">
                <div><span>Ticker</span><span>Shares</span><span>Average cost</span><span>Next target</span><span>State</span></div>
                {positionPlan.length === 0 ? <p>Cash only. The next completed rebalance may create targets.</p> : positionPlan.map((item) => <div key={item.code}><strong>{item.code}</strong><span>{item.shares.toLocaleString()}</span><span>{item.averageCost === null ? "—" : item.averageCost.toFixed(2)}</span><span>{(item.target * 100).toFixed(1)}%</span><span className={`target-state target-state--${item.stateKey}`}>{item.state}</span></div>)}
              </div>
            </section>
            <section className="atlas-panel">
              <header><ShieldAlert size={16} /><span><strong>Risk control ledger</strong><small>Latest ten interventions; never hidden from performance</small></span></header>
              <div className="risk-ledger">
                {selected.snapshots.flatMap((snapshot) => snapshot.riskInterventions.map((event) => ({ event, snapshotDate: snapshot.asOfDate }))).slice(-10).reverse().map(({ event, snapshotDate }, index) => <article key={`${snapshotDate}-${index}`}><span>{snapshotDate}</span><strong>{typeof event.rule === "string" ? event.rule.replace(/_/g, " ") : "risk rule"}</strong><p>{detail(event.detail)}</p></article>)}
                {selected.snapshots.every((snapshot) => snapshot.riskInterventions.length === 0) && <p className="risk-ledger__empty">No risk limit has fired yet. This is not evidence that the strategy is safe.</p>}
              </div>
            </section>
          </div>

          <section className="atlas-panel execution-ledger">
            <header>
              <ListChecks aria-hidden="true" size={16} />
              <span><strong>Execution ledger</strong><small>{executions.length} recorded paper {executions.length === 1 ? "trade" : "trades"} · newest first</small></span>
              <span className="execution-ledger__model">EOD shadow model</span>
            </header>
            <div className="execution-ledger__notice">
              Targets are fixed after the prior close and filled at the next completed session's adjusted open, with configured slippage and fees. These are Atlas simulations, not broker orders or Hedge intraday-agent trades.
            </div>
            {executions.length === 0 ? (
              <p className="execution-ledger__empty">No execution has occurred yet. The book remains in cash until the registered strategy produces an executable target.</p>
            ) : (
              <div className="execution-ledger__table">
                <div><span>Date</span><span>Security</span><span>Side</span><span>Quantity</span><span>Fill</span><span>Gross</span><span>Fee</span><span>Cash impact</span><span>Reason</span></div>
                {executions.map((trade) => (
                  <div key={trade.id}>
                    <span>{executionDate(trade.date)}<small>Session {trade.sessionNumber}</small></span>
                    <strong>{trade.code}</strong>
                    <span className={`execution-side execution-side--${trade.side}`}>{trade.side}</span>
                    <span>{trade.quantity.toLocaleString("en-US")}</span>
                    <span>{executionCurrency(trade.fillPrice)}</span>
                    <span>{executionCurrency(trade.grossValue)}</span>
                    <span>{executionCurrency(trade.fee)}</span>
                    <span className={trade.cashImpact >= 0 ? "value-up" : "value-down"}>{trade.cashImpact >= 0 ? "+" : ""}{executionCurrency(trade.cashImpact)}</span>
                    <span title={trade.reason}>{trade.reason === "prior-close shadow target" ? "Prior-close target rebalance" : trade.reason}</span>
                  </div>
                ))}
              </div>
            )}
          </section>

          {selectedAnalytics && (
            <section className="atlas-panel decision-lineage">
              <header>
                <GitBranch aria-hidden="true" size={16} />
                <span><strong>Decision audit</strong><small>Append-only explanation projected from accepted snapshots; accounting remains independent</small></span>
                <span className="execution-ledger__model">Audit projection</span>
              </header>
              {selectedAnalytics.recentEvents.length === 0 ? (
                <p className="execution-ledger__empty">This book predates the decision audit. Historical snapshots remain visible; no event-first history is invented.</p>
              ) : (
                <div className="decision-lineage__list">
                  {selectedAnalytics.recentEvents.slice(0, 30).map((event) => (
                    <article key={event.id}>
                      <span className={`decision-event decision-event--${event.eventType}`}>{event.eventType}</span>
                      <span><strong>{event.code ? `$${event.code}` : "Portfolio"}</strong><small>{event.effectiveDate} · sequence {event.sequence}</small></span>
                      <span><strong>{event.eventState}</strong><small>{event.causedByEventKey ? `caused by ${event.causedByEventKey}` : "root observation"}</small></span>
                    </article>
                  ))}
                </div>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
