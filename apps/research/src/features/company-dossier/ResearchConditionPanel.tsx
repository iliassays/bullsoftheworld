import {
  AlertTriangle,
  Check,
  CircleDot,
  CircleSlash2,
  FlaskConical,
  History,
} from "lucide-react";

import { StatusBadge, type StatusTone } from "../../design-system";
import type {
  ResearchConditionEvaluation,
  ResearchConditionKey,
  ResearchConditionState,
  ResearchConditionWorkbench,
} from "./model";
import { formatObservedValue } from "./research-condition";

interface ResearchConditionPanelProps {
  workbench: ResearchConditionWorkbench;
  selected: ResearchConditionEvaluation;
  onSelect: (key: ResearchConditionKey) => void;
}

const STATE_LABEL: Record<ResearchConditionState, string> = {
  observed: "Observed",
  not_observed: "Not observed",
  unavailable: "Unavailable",
};

const STATE_TONE: Record<ResearchConditionState, StatusTone> = {
  observed: "info",
  not_observed: "neutral",
  unavailable: "warning",
};

function CheckIcon({ passed }: { passed: boolean | null }) {
  if (passed === null) return <CircleSlash2 aria-hidden="true" size={14} />;
  if (passed) return <Check aria-hidden="true" size={14} />;
  return <CircleDot aria-hidden="true" size={14} />;
}

export function ResearchConditionPanel({
  workbench,
  selected,
  onSelect,
}: ResearchConditionPanelProps) {
  const recentTransitions = selected.transitions.slice(-6).reverse();

  return (
    <section className="dossier-panel condition-workbench">
      <header className="dossier-panel__header">
        <span><FlaskConical aria-hidden="true" size={15} /><strong>Research condition canvas</strong></span>
        <small>{workbench.methodologyVersion} · daily · as of {workbench.asOfDate ?? "unavailable"}</small>
      </header>
      <div className="condition-workbench__notice">
        <AlertTriangle aria-hidden="true" size={14} />
        <span><strong>Descriptive completed-session observations.</strong> {workbench.disclaimer}</span>
      </div>
      <div className="condition-workbench__body">
        <nav aria-label="Research conditions" className="condition-workbench__list">
          {workbench.conditions.map((condition) => (
            <button
              aria-current={condition.key === selected.key ? "true" : undefined}
              key={condition.key}
              onClick={() => onSelect(condition.key)}
              type="button"
            >
              <span className="condition-workbench__code">{condition.shortLabel}</span>
              <span><strong>{condition.title}</strong><small>{condition.category} · v{condition.version}</small></span>
              <StatusBadge tone={STATE_TONE[condition.state]}>{STATE_LABEL[condition.state]}</StatusBadge>
            </button>
          ))}
        </nav>

        <div className="condition-workbench__detail">
          <header>
            <span><small>{selected.category}</small><h3>{selected.title}</h3></span>
            <StatusBadge dot tone={STATE_TONE[selected.state]}>{STATE_LABEL[selected.state]}</StatusBadge>
          </header>
          <p className="condition-workbench__summary">{selected.summary}</p>

          <div className="condition-checks" role="table" aria-label={`${selected.title} checks`}>
            <div className="condition-checks__header" role="row">
              <span role="columnheader">Requirement</span>
              <span role="columnheader">Observed</span>
              <span role="columnheader">Expected</span>
            </div>
            {selected.checks.map((check) => (
              <div
                className={`condition-check condition-check--${check.passed === null ? "unknown" : check.passed ? "passed" : "missing"}`}
                key={check.factKey}
                role="row"
              >
                <span role="cell"><CheckIcon passed={check.passed} /><strong>{check.label}</strong></span>
                <span className="tnum" role="cell">{formatObservedValue(check.observed, check.unit)}</span>
                <span className="tnum" role="cell">{check.expected}</span>
              </div>
            ))}
          </div>

          <div className="condition-workbench__narrative">
            <div><span>Why analysts inspect it</span><p>{selected.whyItMatters}</p></div>
            <div><span>What it cannot establish</span><p>{selected.limitation}</p></div>
          </div>

          <footer className="condition-workbench__history">
            <span><History aria-hidden="true" size={13} /><strong>Prior observations</strong><small>Markers {selected.shortLabel}1, {selected.shortLabel}2… are shown on the chart.</small></span>
            {recentTransitions.length > 0 ? (
              <ol>
                {recentTransitions.map((transition) => (
                  <li key={`${transition.date}-${transition.sequence}`}>
                    <b>{selected.shortLabel}{transition.sequence}</b>
                    <span>{transition.date}</span>
                    <small className="tnum">close {transition.close.toFixed(2)}</small>
                  </li>
                ))}
              </ol>
            ) : (
              <p>No completed historical observation is present in the available 252-session window.</p>
            )}
          </footer>
        </div>
      </div>
    </section>
  );
}
