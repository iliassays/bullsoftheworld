import {
  AlertTriangle,
  BookOpenText,
  CalendarClock,
  CheckCircle2,
  CircleDollarSign,
  FileCheck2,
  Scale,
  ShieldAlert,
  UserRound,
} from "lucide-react";
import { useState, type CSSProperties } from "react";
import { Tab, TabList, TabPanel, Tabs, type Key } from "react-aria-components";
import { useNavigate } from "react-router-dom";

import { Button, StatusBadge } from "../../design-system";
import type { ResearchCandidate, ResearchDimension, ResearchFactorSet } from "./model";

const FACTOR_LABELS: Array<{ key: keyof ResearchFactorSet; label: string; inverse?: boolean }> = [
  { key: "quality", label: "Quality" },
  { key: "value", label: "Value" },
  { key: "momentum", label: "Momentum" },
  { key: "risk", label: "Risk burden", inverse: true },
];

function formatValue(candidate: ResearchCandidate, value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: candidate.currency,
    maximumFractionDigits: candidate.currency === "BDT" ? 0 : 2,
  }).format(value);
}

function FactorBars({ candidate }: { candidate: ResearchCandidate }) {
  return (
    <div className="inspector-factors">
      {FACTOR_LABELS.map((factor) => {
        const detail = candidate.factorDetails?.[factor.key] as ResearchDimension | undefined;
        const summary = (
          <>
            <span>
              <small>{factor.label}</small>
              <strong className="tnum">{candidate.factors[factor.key]}</strong>
            </span>
            <span aria-hidden="true" className="inspector-factor__track">
              <span
                className={factor.inverse ? "inspector-factor__fill--risk" : ""}
                style={{ width: `${candidate.factors[factor.key]}%` }}
              />
            </span>
          </>
        );
        if (!detail) {
          return (
            <div className="inspector-factor inspector-factor--static" key={factor.key}>
              <div className="inspector-factor__summary">{summary}</div>
            </div>
          );
        }
        return (
          <details className="inspector-factor" key={factor.key}>
            <summary>{summary}</summary>
            <div className="inspector-factor__detail">
              <p>{detail.explanation}</p>
              <small>Input coverage {Math.round(detail.confidence * 100)}%</small>
              <dl>
                {Object.entries(detail.inputs).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key.replace(/_/g, " ")}</dt>
                    <dd>{value === null ? "missing" : String(value)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </details>
        );
      })}
    </div>
  );
}

export function ResearchInspector({ candidate }: { candidate: ResearchCandidate | null }) {
  const [tab, setTab] = useState("brief");
  const navigate = useNavigate();

  if (!candidate) {
    return (
      <aside className="research-inspector research-inspector--empty">
        <BookOpenText aria-hidden="true" size={24} />
        <strong>Select a security</strong>
        <span>Its research brief and evidence ledger will open here.</span>
      </aside>
    );
  }

  const evidenceTone =
    candidate.evidence.freshness === "fresh"
      ? "positive"
      : candidate.evidence.freshness === "aging"
        ? "warning"
        : "negative";

  return (
    <aside className="research-inspector">
      <header className="research-inspector__header">
        <div>
          <span className={`queue-security__market queue-security__market--${candidate.market.toLowerCase()}`}>
            {candidate.market}
          </span>
          <span>
            <strong>{candidate.ticker}</strong>
            <small>{candidate.company}</small>
          </span>
        </div>
        <span className="research-inspector__priority">
          <small>Research urgency</small>
          <strong className="tnum">{candidate.priority}</strong>
          {candidate.methodologyVersion && <small>{candidate.methodologyVersion}</small>}
        </span>
      </header>

      <div className="research-inspector__owner">
        <UserRound aria-hidden="true" size={14} />
        {candidate.owner ? (
          <span>
            Owned by <strong>{candidate.owner}</strong>
          </span>
        ) : (
          <span>Unassigned</span>
        )}
        <StatusBadge tone={evidenceTone} dot>
          {candidate.evidence.freshness} evidence
        </StatusBadge>
      </div>

      <Tabs
        className="inspector-tabs"
        onSelectionChange={(key: Key) => setTab(String(key))}
        selectedKey={tab}
      >
        <TabList aria-label="Research brief views" className="inspector-tabs__list">
          <Tab className="inspector-tabs__tab" id="brief">
            Brief
          </Tab>
          <Tab className="inspector-tabs__tab" id="evidence">
            Evidence <span>{candidate.evidence.items.length}</span>
          </Tab>
          {candidate.scenarios.length > 0 && (
            <Tab className="inspector-tabs__tab" id="scenarios">
              Scenarios
            </Tab>
          )}
        </TabList>

        <TabPanel className="inspector-tabs__panel" id="brief">
          <section className="inspector-section inspector-section--lead">
            <span className="inspector-section__eyebrow">
              <FileCheck2 aria-hidden="true" size={14} />
              Latest official evidence
            </span>
            <p>{candidate.keyChange}</p>
          </section>
          <section className="inspector-section">
            <span className="inspector-section__eyebrow">
              <Scale aria-hidden="true" size={14} />
              Research framing
            </span>
            <p>{candidate.thesisSummary}</p>
          </section>
          <section className="inspector-section">
            <span className="inspector-section__eyebrow">
              <CalendarClock aria-hidden="true" size={14} />
              Next catalyst
            </span>
            {candidate.catalyst ? (
              <div className="inspector-catalyst">
                <strong>{candidate.catalyst.label}</strong>
                <span>
                  {candidate.catalyst.window} · {candidate.catalyst.confidence}
                </span>
              </div>
            ) : (
              <p>No confirmed upcoming catalyst is recorded in this queue snapshot.</p>
            )}
          </section>
          <section className="inspector-section">
            <span className="inspector-section__eyebrow">Factor lens</span>
            <FactorBars candidate={candidate} />
            {candidate.priorityExplanation && (
              <p className="inspector-methodology">{candidate.priorityExplanation}</p>
            )}
          </section>
          <section className="inspector-section inspector-section--risk">
            <span className="inspector-section__eyebrow">
              <ShieldAlert aria-hidden="true" size={14} />
              Invalidation
            </span>
            <p>{candidate.invalidation}</p>
          </section>
          <section className="inspector-section">
            <span className="inspector-section__eyebrow">
              <CircleDollarSign aria-hidden="true" size={14} />
              Implementation
            </span>
            <dl className="inspector-implementation">
              <div>
                <dt>Avg daily value</dt>
                <dd>{candidate.liquidity.averageDailyValue}</dd>
              </div>
              <div>
                <dt>Mandate capacity</dt>
                <dd>{candidate.liquidity.capacity}</dd>
              </div>
              <div>
                <dt>Estimated exit</dt>
                <dd>{candidate.liquidity.exitDays.toFixed(1)} days</dd>
              </div>
            </dl>
            {candidate.liquidity.basis && <p className="inspector-methodology">{candidate.liquidity.basis}</p>}
          </section>
          <div className="inspector-flags">
            {candidate.flags.map((flag) => (
              <StatusBadge key={flag} tone="negative">
                <AlertTriangle aria-hidden="true" size={11} />
                {flag}
              </StatusBadge>
            ))}
          </div>
        </TabPanel>

        <TabPanel className="inspector-tabs__panel" id="evidence">
          <section className="evidence-health">
            <div>
              <span
                className="evidence-health__ring"
                style={{ "--coverage": `${candidate.evidence.coveragePct * 3.6}deg` } as CSSProperties}
              >
                <strong className="tnum">{candidate.evidence.coveragePct}%</strong>
              </span>
              <span>
                <strong>Evidence coverage</strong>
                <small>
                  {candidate.evidence.counterCount === null
                    ? "Counter-evidence review not run"
                    : `${candidate.evidence.counterCount} counter-evidence items retained`}
                </small>
              </span>
            </div>
            <p>
              Coverage measures required source presence, not whether the investment thesis is correct.
            </p>
          </section>
          {candidate.evidence.requirements && (
            <section className="evidence-requirements" aria-label="Required evidence coverage">
              {candidate.evidence.requirements.map((requirement) => (
                <div
                  className={requirement.present ? "evidence-requirement--present" : "evidence-requirement--missing"}
                  key={requirement.key}
                >
                  {requirement.present ? (
                    <CheckCircle2 aria-hidden="true" size={14} />
                  ) : (
                    <AlertTriangle aria-hidden="true" size={14} />
                  )}
                  <span>
                    <strong>{requirement.label}</strong>
                    <small>{requirement.asOf ? `As of ${requirement.asOf}` : "Not available"}</small>
                  </span>
                </div>
              ))}
            </section>
          )}
          <section className="evidence-list" aria-label="Top evidence items">
            {candidate.evidence.items.map((item, index) => {
              const body = (
                <>
                <span className="evidence-item__index">{String(index + 1).padStart(2, "0")}</span>
                <span className="evidence-item__body">
                  <span>
                    <strong>{item.source}</strong>
                    <StatusBadge tone={item.purpose === "counter" ? "negative" : "neutral"}>
                      {item.purpose}
                    </StatusBadge>
                  </span>
                  <b>{item.title}</b>
                  <small>
                    Published {item.publishedAt} · {item.confidence} source
                  </small>
                </span>
                </>
              );
              return item.url ? (
                <a className="evidence-item" href={item.url} key={item.id} rel="noreferrer" target="_blank">
                  {body}
                </a>
              ) : (
                <article className="evidence-item" key={item.id}>{body}</article>
              );
            })}
          </section>
          <section className="inspector-section inspector-section--risk">
            <span className="inspector-section__eyebrow">
              <AlertTriangle aria-hidden="true" size={14} />
              Evidence scope
            </span>
            <p>
              Queue coverage only checks required source presence. Claim-level support, counter-evidence, and rejection reasons are produced in a versioned dossier, not inferred here.
            </p>
          </section>
        </TabPanel>

        <TabPanel className="inspector-tabs__panel" id="scenarios">
          <section className="scenario-intro">
            <strong>Decision range</strong>
            <p>Illustrative scenarios expose assumptions; they are not price forecasts.</p>
          </section>
          <div className="scenario-list">
            {candidate.scenarios.map((scenario) => (
              <div className={`scenario-row scenario-row--${scenario.id}`} key={scenario.id}>
                <span className="scenario-row__label">{scenario.id}</span>
                <span className="scenario-row__value">
                  <strong className="tnum">{formatValue(candidate, scenario.value)}</strong>
                  <small className={`tnum ${scenario.returnPct >= 0 ? "value-up" : "value-down"}`}>
                    {scenario.returnPct >= 0 ? "+" : ""}
                    {scenario.returnPct}%
                  </small>
                </span>
                <p>{scenario.premise}</p>
              </div>
            ))}
          </div>
          <section className="scenario-weighting">
            <CheckCircle2 aria-hidden="true" size={16} />
            <span>
              <strong>Required next step</strong>
              <small>Verify the assumptions against the newest primary evidence before weighting scenarios.</small>
            </span>
          </section>
        </TabPanel>
      </Tabs>

      <footer className="research-inspector__actions">
        <Button isDisabled variant="secondary">Assign review</Button>
        <Button onPress={() => navigate(`/companies/${encodeURIComponent(candidate.ticker)}`)} variant="primary">
          Open dossier
        </Button>
      </footer>
    </aside>
  );
}
