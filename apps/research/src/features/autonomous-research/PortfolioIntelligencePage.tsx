import { Activity, AlertTriangle, BriefcaseBusiness, ListChecks, RefreshCw, ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";

import { researchDeployment } from "../../app/deployment";
import { Button, SelectField, StatusBadge } from "../../design-system";
import { useResearchWorkspaces } from "../research-queue/useResearchQueue";
import { useShadowPortfolios } from "./hooks";
import { shadowExecutions } from "./model";
import { PerformanceChart } from "./PerformanceChart";

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

function object(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

export function PortfolioIntelligencePage() {
  const workspace = useResearchWorkspaces().data?.[0];
  const portfolios = useShadowPortfolios(workspace?.id);
  const [selectedId, setSelectedId] = useState("");
  const selected = useMemo(() => portfolios.data?.find((item) => item.id === selectedId) ?? portfolios.data?.[0], [portfolios.data, selectedId]);
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
  const initial = selected?.snapshots[0];
  const totalReturn = latest && initial ? (latest.nav / initial.nav - 1) * 100 : 0;
  const benchmarkReturn = latest && initial ? (latest.benchmarkNav / initial.benchmarkNav - 1) * 100 : 0;
  const promotion = object(selected?.configuration.promotion);
  const promotionStatus = typeof promotion?.status === "string" ? promotion.status : "not evaluated";
  const promotionChecks = Array.isArray(promotion?.checks)
    ? promotion.checks.flatMap((value) => {
        const check = object(value);
        return check && typeof check.key === "string" && typeof check.passed === "boolean" ? [check] : [];
      })
    : [];

  if (portfolios.isLoading) return <div aria-label="Loading shadow portfolios" className="research-loading"><span className="research-loading__body" /></div>;
  if (portfolios.isError) return <section className="research-unavailable"><AlertTriangle size={26} /><h1>Portfolio intelligence unavailable</h1><p>{portfolios.error.message}</p><Button onPress={() => portfolios.refetch()}><RefreshCw size={14} />Retry</Button></section>;

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
        </>
      )}
    </div>
  );
}
