import {
  AlertTriangle,
  ArrowLeft,
  BrainCircuit,
  Building2,
  CalendarClock,
  CheckCircle2,
  ExternalLink,
  FileCheck2,
  Gauge,
  Scale,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { researchDeployment } from "../../app/deployment";
import { Button, StatusBadge } from "../../design-system";
import { useResearchWorkspaces } from "../research-queue/useResearchQueue";
import { OptionsLens } from "../options-lens/OptionsLens";
import {
  useResearchRun,
  useResearchRuns,
  useStartCompanyResearch,
} from "../autonomous-research/hooks";
import { autonomousDecision } from "../autonomous-research/model";
import { DossierChart } from "./DossierChart";
import type { ResearchCompanyDossier } from "./model";
import { useCompanyDossier } from "./useCompanyDossier";

function formatTimestamp(timestamp: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(timestamp));
}

function formatNumber(value: number | null, digits = 1): string {
  return value === null
    ? "Not available"
    : new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(value);
}

function formatCurrency(value: number, currency: "BDT" | "USD", compact = false): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    notation: compact ? "compact" : "standard",
    maximumFractionDigits: compact ? 1 : currency === "USD" ? 2 : 1,
  }).format(value);
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="dossier-metric">
      <span>{label}</span>
      <strong className="tnum">{value}</strong>
      {detail && <small>{detail}</small>}
    </div>
  );
}

function FactorMatrix({ dossier }: { dossier: ResearchCompanyDossier }) {
  const factors = dossier.candidate.factors;
  const rows = [
    ["Quality", factors.quality, false],
    ["Value", factors.value, false],
    ["Momentum", factors.momentum, false],
    ["Risk burden", factors.risk, true],
  ] as const;
  return (
    <div className="dossier-factor-matrix">
      {rows.map(([label, value, risk]) => (
        <div key={label}>
          <span>
            <small>{label}</small>
            <strong className={risk ? "value-down tnum" : "tnum"}>{value}</strong>
          </span>
          <span aria-hidden="true">
            <i className={risk ? "dossier-factor-matrix__risk" : ""} style={{ width: `${value}%` }} />
          </span>
        </div>
      ))}
    </div>
  );
}

function OwnershipPanel({ dossier }: { dossier: ResearchCompanyDossier }) {
  const ownership = dossier.reportedOwnership;
  if (!ownership) return null;
  return (
    <section className="dossier-panel">
      <header className="dossier-panel__header">
        <span>
          <Building2 aria-hidden="true" size={15} />
          <strong>Reported ownership</strong>
        </span>
        <small>As of {ownership.asOfDate}</small>
      </header>
      <div className="ownership-composition" aria-label="Reported ownership composition">
        {ownership.categories.map((category) => (
          <span key={category.key} style={{ width: `${category.valuePct}%` }} title={`${category.label}: ${category.valuePct}%`} />
        ))}
      </div>
      <div className="ownership-rows">
        {ownership.categories.map((category) => (
          <div key={category.key}>
            <span>{category.label}</span>
            <strong className="tnum">{category.valuePct.toFixed(2)}%</strong>
            <small
              className={
                category.changePp === null
                  ? ""
                  : category.changePp > 0
                    ? "value-up"
                    : category.changePp < 0
                      ? "value-down"
                      : ""
              }
            >
              {category.changePp === null
                ? "No comparison"
                : `${category.changePp > 0 ? "+" : ""}${category.changePp.toFixed(2)} pp`}
            </small>
          </div>
        ))}
      </div>
      <p className="dossier-interpretation">{ownership.interpretation}</p>
      <details className="dossier-limitations">
        <summary>Disclosure limitations</summary>
        <ul>{ownership.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      </details>
    </section>
  );
}

function InstitutionalPanel({ dossier }: { dossier: ResearchCompanyDossier }) {
  const disclosure = dossier.institutionalDisclosure;
  if (!disclosure) return null;
  return (
    <section className="dossier-panel">
      <header className="dossier-panel__header">
        <span>
          <Building2 aria-hidden="true" size={15} />
          <strong>13F-reported activity</strong>
        </span>
        <small>Quarter ended {disclosure.reportDate}</small>
      </header>
      <div className="institutional-summary">
        <Metric label="Managers" value={String(disclosure.managersCount)} detail={`Public by ${disclosure.publicBy}`} />
        <Metric label="Reported value" value={formatCurrency(disclosure.totalValueUsd, "USD", true)} />
        <Metric
          label="Net manager breadth"
          value={disclosure.netBreadthPct === null ? "Not available" : `${disclosure.netBreadthPct > 0 ? "+" : ""}${disclosure.netBreadthPct.toFixed(1)}%`}
          detail={`${disclosure.addingManagers} adding · ${disclosure.reducingManagers} reducing`}
        />
      </div>
      <p className="dossier-interpretation">{disclosure.interpretation}</p>
      <a className="dossier-source-link" href={disclosure.sourceUrl} rel="noreferrer" target="_blank">
        Open primary filing source <ExternalLink aria-hidden="true" size={12} />
      </a>
      <details className="dossier-limitations">
        <summary>13F limitations</summary>
        <ul>{disclosure.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      </details>
    </section>
  );
}

function ShortActivityPanel({ dossier }: { dossier: ResearchCompanyDossier }) {
  const activity = dossier.shortActivity;
  if (!activity) return null;
  return (
    <section className="dossier-panel">
      <header className="dossier-panel__header">
        <span>
          <Gauge aria-hidden="true" size={15} />
          <strong>FINRA short-marked activity</strong>
        </span>
        <small>{activity.asOfDate}</small>
      </header>
      <div className="institutional-summary">
        <Metric label="Latest share" value={`${activity.shortMarkedSharePct.toFixed(1)}%`} />
        <Metric label="20-session average" value={activity.average20Pct === null ? "Building baseline" : `${activity.average20Pct.toFixed(1)}%`} />
        <Metric label="Reported activity" value={activity.activityVs20x === null ? "Not available" : `${activity.activityVs20x.toFixed(2)}x`} detail="versus 20-session volume" />
      </div>
      <p className="dossier-interpretation">{activity.interpretation}</p>
      <a className="dossier-source-link" href={activity.sourceUrl} rel="noreferrer" target="_blank">
        Open FINRA source file <ExternalLink aria-hidden="true" size={12} />
      </a>
      <details className="dossier-limitations">
        <summary>FINRA data limitations</summary>
        <ul>{activity.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      </details>
    </section>
  );
}

export function CompanyDossierPage() {
  const { ticker } = useParams();
  const workspaces = useResearchWorkspaces();
  const workspace = workspaces.data?.[0];
  const dossierQuery = useCompanyDossier(workspace?.id, ticker);
  const runs = useResearchRuns(workspace?.id);
  const latestSummary = runs.data?.find(
    (run) => run.runKind === "deep_research" && run.code === ticker?.toUpperCase(),
  );
  const latestRun = useResearchRun(workspace?.id, latestSummary?.id);
  const startResearch = useStartCompanyResearch(workspace?.id);
  const analystRun = startResearch.data ?? latestRun.data;
  const decision = autonomousDecision(analystRun);

  if (workspaces.isLoading || (workspace && dossierQuery.isLoading)) {
    return <div aria-label="Loading company dossier" className="dossier-loading" />;
  }
  if (!workspace || workspaces.isError || dossierQuery.isError || !dossierQuery.data) {
    return (
      <section className="research-unavailable">
        <AlertTriangle aria-hidden="true" size={26} />
        <h1>Company dossier unavailable</h1>
        <p>The secured dossier could not be assembled. No stale or cross-tenant data was substituted.</p>
        <Button onPress={() => (workspaces.isError ? workspaces.refetch() : dossierQuery.refetch())}>
          <RefreshCw aria-hidden="true" size={15} /> Retry
        </Button>
      </section>
    );
  }

  const dossier = dossierQuery.data;
  const candidate = dossier.candidate;
  const currency = candidate.currency;
  const evidenceTone = candidate.evidence.freshness === "fresh" ? "positive" : candidate.evidence.freshness === "aging" ? "warning" : "negative";

  return (
    <div className="company-dossier-page">
      <header className="dossier-header">
        <div>
          <Link className="dossier-back" to="/queue"><ArrowLeft aria-hidden="true" size={14} /> Research queue</Link>
          <span className="dossier-header__identity">
            <span className={`queue-security__market queue-security__market--${candidate.market.toLowerCase()}`}>{candidate.market}</span>
            <span><h1>{candidate.ticker}</h1><p>{candidate.company} · {candidate.sector}</p></span>
          </span>
        </div>
        <div className="dossier-header__meta">
          <StatusBadge tone={evidenceTone} dot>{candidate.evidence.freshness} evidence</StatusBadge>
          <span>Knowledge cutoff<strong>{formatTimestamp(dossier.knowledgeCutoffAt)}</strong></span>
        </div>
      </header>

      <section className="dossier-key-metrics" aria-label="Company research snapshot">
        <Metric label="Last EOD close" value={formatCurrency(candidate.price, currency)} detail={dossier.marketData.asOfDate} />
        <Metric label="Research priority" value={`${candidate.priority}/100`} detail="analyst attention, not return" />
        <Metric label="Market capitalization" value={dossier.marketData.marketCapMn === null ? "Not available" : formatCurrency(dossier.marketData.marketCapMn * 1_000_000, currency, true)} detail={candidate.capTier.replace("_", " ")} />
        <Metric label="Evidence coverage" value={`${candidate.evidence.coveragePct}%`} detail={`${candidate.evidence.sourceCount} official records`} />
        <Metric label="Implementation capacity" value={candidate.liquidity.capacity} detail={`${candidate.liquidity.exitDays.toFixed(1)}-session exit policy`} />
      </section>

      {dossier.dataQualityNotes.length > 0 && (
        <section className="dossier-quality-banner">
          <AlertTriangle aria-hidden="true" size={15} />
          <span><strong>Research limitations</strong>{dossier.dataQualityNotes.join(" ")}</span>
        </section>
      )}

      <section className="dossier-panel autonomous-analyst">
        <header className="dossier-panel__header">
          <span><BrainCircuit aria-hidden="true" size={15} /><strong>Autonomous analyst loop</strong></span>
          <span className="autonomous-analyst__action">
            {decision && <StatusBadge tone={decision.status === "qualified" ? "positive" : decision.status === "monitor" ? "warning" : "negative"} dot>{decision.status} · {(decision.confidence * 100).toFixed(0)}% claim support</StatusBadge>}
            <Button isDisabled={startResearch.isPending} onPress={() => startResearch.mutate(candidate.ticker)} variant="primary">
              <BrainCircuit aria-hidden="true" size={14} />{startResearch.isPending ? "Running analyst, skeptic, verifier…" : decision ? "Re-run with current evidence" : "Run autonomous analyst"}
            </Button>
          </span>
        </header>
        {decision ? (
          <div className="autonomous-analyst__body">
            <div className="autonomous-analyst__verdict"><span>Bounded verdict</span><h2>{decision.headline}</h2><p>{decision.thesis}</p></div>
            <div className="autonomous-analyst__counter"><span><Scale size={13} /> Independent skeptic</span><p>{decision.counterThesis}</p></div>
            {decision.lenses.length > 0 && (
              <div className="autonomous-analyst__lenses">
                <div className="autonomous-analyst__section-title"><strong>Financial reasoning</strong><small>Registered rules over the current fact ledger</small></div>
                <div>
                  {decision.lenses.map((lens) => (
                    <article key={lens.key}>
                      <span className={`reasoning-assessment reasoning-assessment--${lens.assessment}`}>{lens.assessment}</span>
                      <strong>{lens.label}</strong>
                      <p>{lens.summary}</p>
                    </article>
                  ))}
                </div>
              </div>
            )}
            {decision.scenarios.length > 0 && (
              <div className="autonomous-analyst__scenarios">
                <div className="autonomous-analyst__section-title"><strong>Conditional scenario map</strong><small>No probability or target price is manufactured</small></div>
                <div>
                  {decision.scenarios.map((scenario) => (
                    <article className={`research-scenario research-scenario--${scenario.key}`} key={scenario.key}>
                      <span>{scenario.state}</span>
                      <strong>{scenario.title}</strong>
                      <p>{scenario.condition}</p>
                      <small>{scenario.implication}</small>
                      <ul>{scenario.watchItems.map((item) => <li key={item}>{item}</li>)}</ul>
                    </article>
                  ))}
                </div>
              </div>
            )}
            <div className="autonomous-analyst__columns">
              <div><strong>Hard invalidation rules</strong>{decision.invalidationRules.map((rule) => <p key={rule}>{rule}</p>)}</div>
              <div>
                <strong>Next evidence to resolve</strong>
                {decision.nextEvidence.length
                  ? decision.nextEvidence.map((item) => <p key={item.question}><b>{item.priority}</b>{item.question}<small>{item.reason}</small></p>)
                  : decision.missingEvidence.length
                    ? decision.missingEvidence.map((item) => <p key={item}>{item}</p>)
                    : <p>No declared evidence gap cleared the decision gate.</p>}
              </div>
            </div>
            <footer><span>Plan</span><i /> <span>Collect</span><i /> <span>Analyst</span><i /> <span>Skeptic</span><i /> <span>Verify</span><i /> <span>Decision</span><small>{analystRun?.codeVersion}</small></footer>
          </div>
        ) : (
          <div className="autonomous-analyst__empty"><p>No machine verdict exists for this evidence cutoff. Run the bounded loop to create an immutable thesis, counter-thesis, verification record, and 5/20/60-session outcome observations.</p>{startResearch.isError && <span className="atlas-error"><AlertTriangle size={13} />{startResearch.error.message}</span>}</div>
        )}
      </section>

      <div className="dossier-layout">
        <div className="dossier-main-column">
          <section className="dossier-panel dossier-panel--chart">
            <header className="dossier-panel__header">
              <span><Gauge aria-hidden="true" size={15} /><strong>Price and participation</strong></span>
              <small>{dossier.priceHistory.length} completed sessions · adjusted close where available</small>
            </header>
            <DossierChart points={dossier.priceHistory} />
            <div className="dossier-chart-stats">
              <Metric label="52-week range" value={`${formatNumber(dossier.marketData.week52Low, 2)} – ${formatNumber(dossier.marketData.week52High, 2)}`} />
              <Metric label="Relative volume" value={dossier.marketData.relativeVolume === null ? "Not available" : `${dossier.marketData.relativeVolume.toFixed(2)}x`} />
              <Metric label="RSI (14)" value={formatNumber(dossier.marketData.rsi14, 1)} />
              <Metric label="Annualized volatility" value={dossier.marketData.volatilityPct === null ? "Not available" : `${dossier.marketData.volatilityPct.toFixed(1)}%`} />
            </div>
          </section>

          <section className="dossier-panel dossier-decision-frame">
            <header className="dossier-panel__header">
              <span><FileCheck2 aria-hidden="true" size={15} /><strong>Decision frame</strong></span>
              <small>{candidate.methodologyVersion}</small>
            </header>
            <div className="dossier-decision-frame__lead"><span>Latest official evidence</span><p>{candidate.keyChange}</p></div>
            <div className="dossier-decision-grid">
              <div><span>Why it is in the queue</span><p>{candidate.queueReason}</p></div>
              <div><span>Current framing</span><p>{candidate.thesisSummary}</p></div>
              <div className="dossier-decision-grid__risk"><span><ShieldAlert aria-hidden="true" size={13} /> Invalidation state</span><p>{candidate.invalidation}</p></div>
              <FactorMatrix dossier={dossier} />
            </div>
          </section>

          <section className="dossier-panel">
            <header className="dossier-panel__header">
              <span><FileCheck2 aria-hidden="true" size={15} /><strong>Official evidence ledger</strong></span>
              <small>{candidate.evidence.items.length} most relevant records shown</small>
            </header>
            <div className="dossier-evidence-list">
              {candidate.evidence.items.map((item, index) => {
                const content = <><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{item.title}</strong><small>{item.source} · published {item.publishedAt} · {item.purpose}</small></div>{item.url && <ExternalLink aria-hidden="true" size={13} />}</>;
                return item.url ? <a href={item.url} key={item.id} rel="noreferrer" target="_blank">{content}</a> : <article key={item.id}>{content}</article>;
              })}
            </div>
            <div className="dossier-requirements">
              {candidate.evidence.requirements?.map((requirement) => (
                <span className={requirement.present ? "" : "dossier-requirement--missing"} key={requirement.key}>
                  {requirement.present ? <CheckCircle2 aria-hidden="true" size={12} /> : <AlertTriangle aria-hidden="true" size={12} />}
                  {requirement.label}<small>{requirement.asOf ?? "missing"}</small>
                </span>
              ))}
            </div>
          </section>
        </div>

        <aside className="dossier-side-column">
          <section className="dossier-panel">
            <header className="dossier-panel__header"><span><Gauge aria-hidden="true" size={15} /><strong>Fundamental snapshot</strong></span><small>As of {dossier.marketData.asOfDate}</small></header>
            <dl className="dossier-fundamentals">
              <div><dt>P/E</dt><dd>{formatNumber(dossier.fundamentals.peRatio, 2)}</dd></div>
              <div><dt>P/B</dt><dd>{formatNumber(dossier.fundamentals.pbRatio, 2)}</dd></div>
              <div><dt>ROE</dt><dd>{dossier.fundamentals.roePct === null ? "Not available" : `${dossier.fundamentals.roePct.toFixed(1)}%`}</dd></div>
              <div><dt>EPS growth YoY</dt><dd>{dossier.fundamentals.epsGrowthYoyPct === null ? "Not available" : `${dossier.fundamentals.epsGrowthYoyPct.toFixed(1)}%`}</dd></div>
              <div><dt>Dividend yield</dt><dd>{dossier.fundamentals.dividendYieldPct === null ? "Not available" : `${dossier.fundamentals.dividendYieldPct.toFixed(1)}%`}</dd></div>
              <div><dt>P/E vs sector</dt><dd>{dossier.fundamentals.peVsSector === null ? "Not available" : `${dossier.fundamentals.peVsSector.toFixed(2)}x`}</dd></div>
            </dl>
            <p className="dossier-interpretation">These are descriptive normalized inputs, not a valuation conclusion or target price.</p>
          </section>
          <OwnershipPanel dossier={dossier} />
          <InstitutionalPanel dossier={dossier} />
          <ShortActivityPanel dossier={dossier} />
          <OptionsLens workspaceId={workspace.id} code={candidate.ticker} />
          <section className="dossier-panel dossier-panel--policy">
            <header className="dossier-panel__header"><span><CalendarClock aria-hidden="true" size={15} /><strong>Research record</strong></span></header>
            <p>Generated {formatTimestamp(dossier.generatedAt)} for the {researchDeployment.exchangeName} workspace.</p>
            <p>{candidate.priorityExplanation}</p>
          </section>
        </aside>
      </div>
    </div>
  );
}
