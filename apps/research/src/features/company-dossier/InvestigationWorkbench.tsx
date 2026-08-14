import {
  AlertTriangle,
  BrainCircuit,
  Building2,
  CheckCircle2,
  ChartNoAxesCombined,
  Circle,
  ExternalLink,
  FileCheck2,
  RefreshCw,
  Save,
  SlidersHorizontal,
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";

import type { DecisionEvent } from "../../app/api-client";
import { researchDeployment } from "../../app/deployment";
import { AppTooltip, Button, StatusBadge } from "../../design-system";
import type { AutonomousDecision } from "../autonomous-research/model";
import { DossierChart } from "./DossierChart";
import type { ResearchCompanyDossier, ResearchConditionEvaluation } from "./model";
import type {
  DossierChartMode,
  DossierChartRange,
  DossierChartTimeframe,
} from "./research-condition";
import { formatObservedValue } from "./research-condition";
import {
  DEFAULT_WORKBENCH_PREFERENCES,
  parseWorkbenchPreferences,
  updateOverlayVisibility,
  workbenchStorageKey,
  type WorkbenchInspector,
  type WorkbenchLayout,
  type WorkbenchOverlayKey,
  type WorkbenchPreferences,
} from "./workbench-state";

interface InvestigationWorkbenchProps {
  dossier: ResearchCompanyDossier;
  decision: AutonomousDecision | null;
  decisionEvents: readonly DecisionEvent[];
  selectedCondition: ResearchConditionEvaluation;
  averageCost: number | null;
  mode: DossierChartMode;
  range: DossierChartRange;
  timeframe: DossierChartTimeframe;
  analystRunning: boolean;
  analystError: string | null;
  onConditionChange: (condition: ResearchConditionEvaluation["key"]) => void;
  onModeChange: (mode: DossierChartMode) => void;
  onRangeChange: (range: DossierChartRange) => void;
  onTimeframeChange: (timeframe: DossierChartTimeframe) => void;
  onRunAnalyst: () => void;
}

const LAYOUTS: Array<{ key: WorkbenchLayout; label: string }> = [
  { key: "balanced", label: "Balanced" },
  { key: "chart_focus", label: "Chart focus" },
  { key: "evidence_focus", label: "Evidence focus" },
];

const INSPECTORS: Array<{ key: WorkbenchInspector; label: string }> = [
  { key: "condition", label: "Condition" },
  { key: "evidence", label: "Evidence" },
  { key: "fundamentals", label: "Fundamentals" },
  { key: "analyst", label: "Analyst" },
];

const LAYERS: Array<{ key: WorkbenchOverlayKey; label: string }> = [
  { key: "ema20", label: "EMA20" },
  { key: "ema50", label: "EMA50" },
  { key: "levels", label: "Levels" },
  { key: "condition", label: "Condition" },
  { key: "evidence", label: "Evidence" },
  { key: "portfolio", label: "Portfolio" },
];

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(`${value.slice(0, 10)}T00:00:00Z`));
}

function formatValue(value: number | null, suffix = ""): string {
  return value === null ? "Not available" : `${value.toFixed(2)}${suffix}`;
}

function formatCurrency(value: number, currency: "BDT" | "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: currency === "USD" ? 2 : 1,
  }).format(value);
}

function useWorkbenchPreferences(): [
  WorkbenchPreferences,
  Dispatch<SetStateAction<WorkbenchPreferences>>,
] {
  const storageKey = workbenchStorageKey(researchDeployment.tenant);
  const [preferences, setPreferences] = useState<WorkbenchPreferences>(() => {
    if (typeof window === "undefined") return DEFAULT_WORKBENCH_PREFERENCES;
    try {
      return parseWorkbenchPreferences(window.localStorage.getItem(storageKey));
    } catch {
      return DEFAULT_WORKBENCH_PREFERENCES;
    }
  });
  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(preferences));
    } catch {
      // Browser privacy settings may disable local persistence; the live view remains usable.
    }
  }, [preferences, storageKey]);
  return [preferences, setPreferences];
}

function ConditionInspector({ condition }: { condition: ResearchConditionEvaluation }) {
  const passed = condition.checks.filter((check) => check.passed === true).length;
  return (
    <div className="workbench-inspector__content">
      <div className="workbench-inspector__heading">
        <span>{condition.category} · definition {condition.version}</span>
        <h3>{condition.title}</h3>
        <StatusBadge
          dot
          tone={condition.state === "observed" ? "positive" : condition.state === "unavailable" ? "negative" : "neutral"}
        >
          {condition.state === "observed" ? "Observed" : condition.state === "unavailable" ? "Unavailable" : "Not observed"}
        </StatusBadge>
      </div>
      <p className="workbench-inspector__summary">{condition.summary}</p>
      <div className="workbench-condition-score">
        <strong>{passed}/{condition.checks.length}</strong>
        <span>registered checks met</span>
      </div>
      <div className="workbench-checks" role="table" aria-label={`${condition.title} checks`}>
        {condition.checks.map((check) => {
          const state = check.passed === true
            ? "passed"
            : check.passed === false
              ? "failed"
              : "unavailable";
          return (
            <div data-state={state} key={check.factKey} role="row">
              <span role="cell">
                {check.passed === true
                  ? <CheckCircle2 aria-hidden="true" size={12} />
                  : check.passed === false
                    ? <AlertTriangle aria-hidden="true" size={12} />
                    : <Circle aria-hidden="true" size={12} />}
                {check.label}
              </span>
              <strong role="cell">{formatObservedValue(check.observed, check.unit)}</strong>
              <small role="cell">{check.expected}</small>
            </div>
          );
        })}
      </div>
      <div className="workbench-inspector__narrative">
        <span>Why analysts monitor it</span>
        <p>{condition.whyItMatters}</p>
        <span>What it cannot establish</span>
        <p>{condition.limitation}</p>
      </div>
    </div>
  );
}

function EvidenceInspector({ dossier }: { dossier: ResearchCompanyDossier }) {
  return (
    <div className="workbench-inspector__content">
      <div className="workbench-inspector__heading">
        <span>Known by {formatDate(dossier.knowledgeCutoffAt)}</span>
        <h3>Official evidence</h3>
        <StatusBadge tone={dossier.candidate.evidence.freshness === "fresh" ? "positive" : "warning"} dot>
          {dossier.candidate.evidence.coveragePct}% coverage
        </StatusBadge>
      </div>
      <div className="workbench-evidence-list">
        {dossier.candidate.evidence.items.slice(0, 6).map((item) => {
          const body = (
            <>
              <span>{item.source} · {item.purpose}</span>
              <strong>{item.title}</strong>
              <small>{formatDate(item.publishedAt)} · {item.confidence}</small>
            </>
          );
          return item.url ? (
            <a href={item.url} key={item.id} rel="noreferrer" target="_blank">
              {body}<ExternalLink aria-hidden="true" size={12} />
            </a>
          ) : <article key={item.id}>{body}</article>;
        })}
      </div>
      <div className="workbench-requirements">
        {dossier.candidate.evidence.requirements?.map((requirement) => (
          <span data-present={requirement.present} key={requirement.key}>
            {requirement.label}<small>{requirement.asOf ?? "missing"}</small>
          </span>
        ))}
      </div>
    </div>
  );
}

function FundamentalsInspector({ dossier }: { dossier: ResearchCompanyDossier }) {
  const { fundamentals, marketData } = dossier;
  const rows = [
    ["P/E", formatValue(fundamentals.peRatio)],
    ["P/B", formatValue(fundamentals.pbRatio)],
    ["ROE", formatValue(fundamentals.roePct, "%")],
    ["EPS growth YoY", formatValue(fundamentals.epsGrowthYoyPct, "%")],
    ["Dividend yield", formatValue(fundamentals.dividendYieldPct, "%")],
    ["P/E versus sector", fundamentals.peVsSector === null ? "Not available" : `${fundamentals.peVsSector.toFixed(2)}x`],
    ["RSI (14)", formatValue(marketData.rsi14)],
    ["Relative volume", marketData.relativeVolume === null ? "Not available" : `${marketData.relativeVolume.toFixed(2)}x`],
  ];
  return (
    <div className="workbench-inspector__content">
      <div className="workbench-inspector__heading">
        <span>Snapshot · {formatDate(marketData.asOfDate)}</span>
        <h3>Business and market facts</h3>
        <StatusBadge tone="neutral">Descriptive</StatusBadge>
      </div>
      <dl className="workbench-fundamentals">
        {rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
      </dl>
      <p className="workbench-inspector__footnote">
        Current normalized inputs. They are neither a valuation conclusion nor a target price.
      </p>
    </div>
  );
}

function AnalystInspector({
  decision,
  running,
  error,
  onRun,
}: {
  decision: AutonomousDecision | null;
  running: boolean;
  error: string | null;
  onRun: () => void;
}) {
  return (
    <div className="workbench-inspector__content">
      <div className="workbench-inspector__heading">
        <span>Bounded analyst · skeptic · verifier</span>
        <h3>{decision ? decision.headline : "No current analyst conclusion"}</h3>
        {decision && (
          <StatusBadge tone={decision.status === "qualified" ? "positive" : decision.status === "monitor" ? "warning" : "negative"} dot>
            {decision.status}
          </StatusBadge>
        )}
      </div>
      {decision ? (
        <div className="workbench-analyst-brief">
          <span>Evidence case</span><p>{decision.thesis}</p>
          <span>Independent challenge</span><p>{decision.counterThesis}</p>
          <span>Next unresolved evidence</span>
          <p>{decision.nextEvidence[0]?.question ?? decision.missingEvidence[0] ?? "No declared evidence gap cleared the gate."}</p>
          <span>Trade status</span>
          <p>{decision.strategyKey ? `Attached to ${decision.strategyKey}; risk controls still govern action.` : "Research only; no validated strategy is attached."}</p>
        </div>
      ) : (
        <p className="workbench-inspector__summary">
          Run the bounded loop to create a cited thesis, counter-thesis, verification record, and unresolved-evidence list.
        </p>
      )}
      <Button isDisabled={running} onPress={onRun} variant="primary">
        <BrainCircuit aria-hidden="true" size={14} />
        {running ? "Running analyst…" : decision ? "Refresh analyst record" : "Run autonomous analyst"}
      </Button>
      {error && <p className="atlas-error">{error}</p>}
    </div>
  );
}

export function InvestigationWorkbench({
  dossier,
  decision,
  decisionEvents,
  selectedCondition,
  averageCost,
  mode,
  range,
  timeframe,
  analystRunning,
  analystError,
  onConditionChange,
  onModeChange,
  onRangeChange,
  onTimeframeChange,
  onRunAnalyst,
}: InvestigationWorkbenchProps) {
  const [preferences, setPreferences] = useWorkbenchPreferences();
  const candidate = dossier.candidate;
  const timeline = useMemo(() => {
    const items = [
      ...selectedCondition.transitions.map((item) => ({
        id: `condition-${item.sequence}-${item.date}`,
        date: item.date,
        kind: selectedCondition.shortLabel,
        title: `${selectedCondition.title} observed`,
        detail: `Episode ${item.sequence} · close ${formatCurrency(item.close, candidate.currency)}`,
        url: null as string | null,
      })),
      ...candidate.evidence.items.map((item) => ({
        id: `evidence-${item.id}`,
        date: item.publishedAt.slice(0, 10),
        kind: "E",
        title: item.title,
        detail: `${item.source} · ${item.purpose}`,
        url: item.url ?? null,
      })),
      ...decisionEvents.map((item) => ({
        id: `decision-${item.id}`,
        date: item.effectiveDate,
        kind: item.eventType.slice(0, 1).toUpperCase(),
        title: `${item.eventType} · ${item.eventState.replaceAll("_", " ")}`,
        detail: String(item.payload.action ?? item.payload.reason ?? "Portfolio decision event"),
        url: null as string | null,
      })),
    ];
    return items.sort((left, right) => right.date.localeCompare(left.date)).slice(0, 8);
  }, [candidate.currency, candidate.evidence.items, decisionEvents, selectedCondition]);

  const updateLayout = (layout: WorkbenchLayout) => setPreferences((current) => ({ ...current, layout }));
  const updateInspector = (inspector: WorkbenchInspector) => setPreferences((current) => ({ ...current, inspector }));
  const toggleLayer = (key: WorkbenchOverlayKey) => setPreferences((current) => ({
    ...current,
    overlays: updateOverlayVisibility(current.overlays, key),
  }));
  const reset = () => setPreferences(DEFAULT_WORKBENCH_PREFERENCES);

  return (
    <section
      aria-label="Atlas investigation workbench"
      className={`investigation-workbench investigation-workbench--${preferences.layout}`}
    >
      <header className="investigation-workbench__header">
        <div>
          <span><ChartNoAxesCombined aria-hidden="true" size={15} /> Investigation workbench</span>
          <strong>{candidate.ticker} · synchronized market and company evidence</strong>
          <small>Completed-session data through {formatDate(dossier.marketData.asOfDate)} · {dossier.conditionWorkbench.methodologyVersion}</small>
        </div>
        <div className="investigation-workbench__header-actions">
          <span className="workbench-saved"><Save aria-hidden="true" size={12} /> View saved on this device</span>
          <div aria-label="Workbench layout" className="workbench-segments" role="radiogroup">
            {LAYOUTS.map((layout) => (
              <button
                aria-checked={preferences.layout === layout.key}
                key={layout.key}
                onClick={() => updateLayout(layout.key)}
                role="radio"
                type="button"
              >
                {layout.label}
              </button>
            ))}
          </div>
          <AppTooltip label="Restore the default workbench layout and chart layers">
            <button aria-label="Reset workbench view" className="workbench-reset" onClick={reset} type="button">
              <RefreshCw aria-hidden="true" size={14} />
            </button>
          </AppTooltip>
        </div>
      </header>

      <div className="investigation-workbench__layers">
        <span><SlidersHorizontal aria-hidden="true" size={13} /> Chart layers</span>
        <div>
          {LAYERS.map((layer) => (
            <button
              aria-pressed={preferences.overlays[layer.key]}
              key={layer.key}
              onClick={() => toggleLayer(layer.key)}
              type="button"
            >
              {layer.label}
            </button>
          ))}
        </div>
        <small>{timeframe === "1W" ? "Weekly bars aggregate completed daily records." : "Daily bars are the stored source records."}</small>
      </div>

      <div className="investigation-workbench__body">
        <nav aria-label="Research condition context" className="workbench-context-rail">
          <header><span>Research conditions</span><small>Selecting one updates the chart and inspector</small></header>
          {dossier.conditionWorkbench.conditions.map((condition) => (
            <button
              aria-current={condition.key === selectedCondition.key}
              key={condition.key}
              onClick={() => onConditionChange(condition.key)}
              type="button"
            >
              <span>{condition.shortLabel}</span>
              <span><strong>{condition.title}</strong><small>{condition.category} · v{condition.version}</small></span>
              <i data-state={condition.state}>{condition.state === "observed" ? "Observed" : condition.state === "unavailable" ? "Unavailable" : "Not observed"}</i>
            </button>
          ))}
          <div className="workbench-context-rail__facts">
            <span><strong>{candidate.evidence.sourceCount}</strong> evidence records</span>
            <span><strong>{selectedCondition.transitions.length}</strong> recorded episodes</span>
            <span><strong>{decisionEvents.length}</strong> portfolio events</span>
          </div>
        </nav>

        <section className="workbench-chart-pane">
          <header>
            <span><strong>Price, participation and decision context</strong><small>{dossier.priceHistory.length} completed source sessions · {dossier.marketData.benchmarkCode} benchmark</small></span>
            <StatusBadge tone={candidate.evidence.freshness === "fresh" ? "positive" : "warning"} dot>{candidate.evidence.freshness} evidence</StatusBadge>
          </header>
          <DossierChart
            averageCost={averageCost}
            benchmarkCode={dossier.marketData.benchmarkCode}
            decisionEvents={decisionEvents}
            evidence={candidate.evidence.items}
            mode={mode}
            onModeChange={onModeChange}
            onRangeChange={onRangeChange}
            onTimeframeChange={onTimeframeChange}
            overlays={dossier.conditionWorkbench.overlays}
            points={dossier.priceHistory}
            range={range}
            resistance={dossier.marketData.nearestResistance}
            selectedCondition={selectedCondition}
            support={dossier.marketData.nearestSupport}
            timeframe={timeframe}
            visibility={preferences.overlays}
          />
          <div className="workbench-market-strip">
            <span><small>Last close</small><strong>{formatCurrency(candidate.price, candidate.currency)}</strong></span>
            <span><small>Relative volume</small><strong>{dossier.marketData.relativeVolume === null ? "N/A" : `${dossier.marketData.relativeVolume.toFixed(2)}x`}</strong></span>
            <span><small>RSI (14)</small><strong>{dossier.marketData.rsi14 === null ? "N/A" : dossier.marketData.rsi14.toFixed(1)}</strong></span>
            <span><small>CMF / OBV slope</small><strong>{formatValue(dossier.marketData.cmf20)} / {formatValue(dossier.marketData.obvSlope)}</strong></span>
          </div>
        </section>

        <aside className="workbench-inspector" aria-label="Synchronized research inspector">
          <div aria-label="Inspector view" className="workbench-inspector__tabs" role="tablist">
            {INSPECTORS.map((inspector) => (
              <button
                aria-selected={preferences.inspector === inspector.key}
                key={inspector.key}
                onClick={() => updateInspector(inspector.key)}
                role="tab"
                type="button"
              >
                {inspector.label}
              </button>
            ))}
          </div>
          {preferences.inspector === "condition" && <ConditionInspector condition={selectedCondition} />}
          {preferences.inspector === "evidence" && <EvidenceInspector dossier={dossier} />}
          {preferences.inspector === "fundamentals" && <FundamentalsInspector dossier={dossier} />}
          {preferences.inspector === "analyst" && (
            <AnalystInspector decision={decision} error={analystError} onRun={onRunAnalyst} running={analystRunning} />
          )}
        </aside>
      </div>

      <div className="workbench-timeline">
        <header><FileCheck2 aria-hidden="true" size={13} /><span>Evidence timeline</span><small>Newest known event first</small></header>
        <div>
          {timeline.map((item) => {
            const content = <><i>{item.kind}</i><span><strong>{item.title}</strong><small>{formatDate(item.date)} · {item.detail}</small></span></>;
            return item.url
              ? <a href={item.url} key={item.id} rel="noreferrer" target="_blank">{content}</a>
              : <article key={item.id}>{content}</article>;
          })}
          {!timeline.length && <p>No timestamped condition, evidence, or portfolio event is available.</p>}
        </div>
      </div>

      <footer className="investigation-workbench__footer">
        <span><Building2 aria-hidden="true" size={12} /> {researchDeployment.exchangeName} tenant boundary</span>
        <span>{dossier.conditionWorkbench.disclaimer}</span>
      </footer>
    </section>
  );
}
