import { Ban, FlaskConical, ShieldCheck } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { researchApi, type StrategyReadinessEntry } from "../../app/api-client";
import { isResearchPreview } from "../../app/deployment";
import { StatusBadge, type StatusTone } from "../../design-system";
import { previewStrategyReadiness } from "./preview-data";

const STATUS_LABEL: Record<StrategyReadinessEntry["status"], string> = {
  backtest_ready: "Backtest ready",
  diagnostic_only: "Diagnostic only",
  blocked: "Blocked",
};

const STATUS_TONE: Record<StrategyReadinessEntry["status"], StatusTone> = {
  backtest_ready: "positive",
  diagnostic_only: "warning",
  blocked: "negative",
};

function StatusIcon({ status }: { status: StrategyReadinessEntry["status"] }) {
  if (status === "backtest_ready") return <ShieldCheck aria-hidden="true" size={15} />;
  if (status === "diagnostic_only") return <FlaskConical aria-hidden="true" size={15} />;
  return <Ban aria-hidden="true" size={15} />;
}

export function StrategyReadinessPanel() {
  const [expandedKey, setExpandedKey] = useState<string>();
  const readiness = useQuery({
    queryKey: ["research", "strategy-readiness"],
    queryFn: () =>
      isResearchPreview
        ? Promise.resolve(previewStrategyReadiness)
        : researchApi.strategyReadiness(),
    staleTime: 60 * 60 * 1000,
  });

  if (readiness.isLoading || readiness.isError || !readiness.data) return null;
  const entries = [...readiness.data.entries].sort((left, right) => {
    const order = { backtest_ready: 0, diagnostic_only: 1, blocked: 2 } as const;
    return order[left.status] - order[right.status] || left.name.localeCompare(right.name);
  });

  return (
    <section className="atlas-panel strategy-readiness">
      <header className="strategy-readiness__header">
        <span>
          <strong>What Atlas will and will not trade</strong>
          <small>
            Every evaluated strategy family with its audited evidence status. Blocked and
            diagnostic entries name the exact missing datasets.
          </small>
        </span>
      </header>
      <div className="strategy-readiness__list" role="list">
        {entries.map((entry) => {
          const expanded = expandedKey === entry.key;
          return (
            <div className="strategy-readiness__entry" key={entry.key} role="listitem">
              <button
                aria-expanded={expanded}
                onClick={() => setExpandedKey(expanded ? undefined : entry.key)}
                type="button"
              >
                <span className={`strategy-readiness__icon strategy-readiness__icon--${entry.status}`}>
                  <StatusIcon status={entry.status} />
                </span>
                <span className="strategy-readiness__identity">
                  <strong>{entry.name}</strong>
                  <small>
                    {entry.direction.replace("_", "/")} · {entry.horizon}
                    {entry.implementedStrategyKey ? " · implemented" : " · not implemented"}
                  </small>
                </span>
                <StatusBadge tone={STATUS_TONE[entry.status]}>
                  {STATUS_LABEL[entry.status]}
                </StatusBadge>
              </button>
              {expanded && (
                <div className="strategy-readiness__detail">
                  <p><b>Hypothesis.</b> {entry.economicHypothesis}</p>
                  <p><b>Why this status.</b> {entry.rationale}</p>
                  {entry.missingData.length > 0 && (
                    <ul>
                      {entry.missingData.map((item) => (
                        <li key={item.key}>{item.description}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <p className="strategy-readiness__method">{readiness.data.methodology}</p>
    </section>
  );
}
