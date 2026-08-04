import { AlertTriangle, Database, FlaskConical, ShieldX } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { ModelHorizon, ModelWindowMetrics } from "../../app/api-client";
import { StatusBadge } from "../../design-system";
import { useModelExperiment } from "./hooks";

function metric(value: number | null | undefined, suffix = ""): string {
  return value === null || value === undefined ? "Not available" : `${value.toFixed(2)}${suffix}`;
}

function signed(value: number | null | undefined, suffix = "%"): string {
  if (value === null || value === undefined) return "Not available";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}${suffix}`;
}

function verdictLabel(value: string): string {
  return value === "promising_diagnostic_but_data_blocked"
    ? "Promising diagnostic · blocked"
    : "Rejected by current test";
}

function ComparisonRow({ label, model, baseline }: {
  label: string;
  model: number | null | undefined;
  baseline: number | null | undefined;
}) {
  return (
    <div role="row">
      <strong>{label}</strong>
      <span className={(model ?? 0) >= 0 ? "value-up" : "value-down"}>{signed(model)}</span>
      <span className={(baseline ?? 0) >= 0 ? "value-up" : "value-down"}>{signed(baseline)}</span>
    </div>
  );
}

function HoldoutStory({ horizon }: { horizon: ModelHorizon }) {
  const holdout: ModelWindowMetrics | null = horizon.holdout;
  const baseline = horizon.momentumHoldout;
  const coefficientScale = Math.max(
    ...horizon.topCoefficients.map((item) => Math.abs(item.coefficient)),
    0.000001,
  );
  return (
    <div className="model-audit__horizon">
      <div className="model-audit__story">
        <span><small>01 · Test</small><strong>{horizon.horizonSessions}-session ranking</strong><p>Signal at a completed close; modeled entry begins at the next session open.</p></span>
        <span><small>02 · Untouched holdout</small><strong>{holdout?.dates ?? 0} rebalance dates</strong><p>{(holdout?.trades ?? 0).toLocaleString()} modeled selections after the 2024 validation cutoff.</p></span>
        <span><small>03 · Result after costs</small><strong className={(holdout?.meanStressedPct ?? 0) >= 0 ? "value-up" : "value-down"}>{signed(holdout?.meanStressedPct)}</strong><p>Mean SPY-relative return with transaction costs doubled.</p></span>
        <span><small>04 · Research decision</small><strong>{verdictLabel(horizon.researchVerdict)}</strong><p>No target, paper trade, or order is created from this experiment.</p></span>
      </div>

      <div className="model-audit__comparison">
        <div className="model-audit__table" role="table" aria-label="Model holdout comparison">
          <div role="row"><span>Untouched holdout</span><span>Rank model</span><span>Naive momentum</span></div>
          <ComparisonRow label="Mean net / rebalance" model={holdout?.meanNetPct} baseline={baseline?.meanNetPct} />
          <ComparisonRow label="Stressed net / rebalance" model={holdout?.meanStressedPct} baseline={baseline?.meanStressedPct} />
          <ComparisonRow label="Annualized net" model={holdout?.annualizedNetPct} baseline={baseline?.annualizedNetPct} />
          <ComparisonRow label="Maximum drawdown" model={holdout?.maximumDrawdownPct} baseline={baseline?.maximumDrawdownPct} />
          <div role="row"><strong>Sharpe</strong><span>{metric(holdout?.sharpe, "")}</span><span>{metric(baseline?.sharpe, "")}</span></div>
          <div role="row"><strong>Positive periods</strong><span>{metric(holdout?.hitRatePct, "%")}</span><span>{metric(baseline?.hitRatePct, "%")}</span></div>
        </div>
        <div className="model-audit__drivers">
          <strong>Largest fitted drivers</strong>
          <small>Direction and relative weight, not causal importance</small>
          {horizon.topCoefficients.map((item) => (
            <span key={item.feature}>
              <label>{item.feature.replaceAll("_", " ")}</label>
              <i><b style={{ width: `${Math.abs(item.coefficient) / coefficientScale * 100}%` }} /></i>
              <em className={item.coefficient >= 0 ? "value-up" : "value-down"}>{item.coefficient.toFixed(4)}</em>
            </span>
          ))}
        </div>
      </div>

      <div className="model-audit__blockers">
        <ShieldX aria-hidden="true" size={16} />
        <span><strong>Promotion is blocked</strong><small>{horizon.promotionBlockers.join(" · ")}</small></span>
      </div>
    </div>
  );
}

export function ModelExperimentPanel() {
  const board = useModelExperiment();
  const horizons = board.data?.experiment?.horizons ?? [];
  const [selected, setSelected] = useState<number>();
  useEffect(() => {
    const firstHorizon = horizons[0]?.horizonSessions;
    if (firstHorizon !== undefined && !horizons.some((item) => item.horizonSessions === selected)) {
      setSelected(firstHorizon);
    }
  }, [horizons, selected]);
  const horizon = useMemo(
    () => horizons.find((item) => item.horizonSessions === selected) ?? horizons[0],
    [horizons, selected],
  );

  if (board.isLoading) {
    return <section className="atlas-panel model-audit model-audit--loading" aria-label="Loading statistical model audit" />;
  }
  if (board.isError || !board.data) {
    return (
      <section className="atlas-panel model-audit">
        <header><AlertTriangle aria-hidden="true" size={16} /><span><strong>Statistical model audit unavailable</strong><small>The rest of Strategy Lab remains usable</small></span><StatusBadge tone="negative">API error</StatusBadge></header>
        <p className="model-audit__notice">Atlas could not load the model registry. No model output was substituted from another market.</p>
      </section>
    );
  }

  const { foundation, experiment } = board.data;
  return (
    <section className="atlas-panel model-audit">
      <header>
        <FlaskConical aria-hidden="true" size={16} />
        <span><strong>Statistical model audit</strong><small>Offline evaluation · isolated from Agent decisions</small></span>
        <StatusBadge tone={experiment?.status === "diagnostic" ? "warning" : "negative"} dot>
          {experiment ? (experiment.status === "diagnostic" ? "Diagnostic only" : "Rejected") : "Not run"}
        </StatusBadge>
      </header>

      <div className="model-audit__foundation">
        <Database aria-hidden="true" size={16} />
        {foundation ? (
          <>
            <span><small>Certified universe</small><strong>{foundation.asOfDate}</strong></span>
            <span><small>Research eligible</small><strong>{foundation.eligibleCount.toLocaleString()} / {foundation.candidateCount.toLocaleString()}</strong></span>
            <span><small>Model eligible</small><strong>{foundation.modelEligibleCount.toLocaleString()}</strong></span>
            <span><small>Evidence mode</small><strong>{foundation.sourceMode.replaceAll("_", " ")}</strong></span>
          </>
        ) : <span><small>Certified universe</small><strong>No snapshot is available</strong></span>}
      </div>

      {!experiment ? (
        <div className="model-audit__notice">
          <strong>No market-bound statistical experiment has been published.</strong>
          <p>The data foundation is visible above. Atlas will not invent performance or reuse the other market&apos;s model.</p>
          {foundation && Object.entries(foundation.modelBlockers).slice(0, 4).map(([key, count]) => (
            <span key={key}>{key.replaceAll("_", " ")} · {count.toLocaleString()} securities</span>
          ))}
        </div>
      ) : (
        <>
          <div className="model-audit__meta">
            <span><small>Data cutoff</small><strong>{experiment.dataCutoff}</strong></span>
            <span><small>Symbols evaluated</small><strong>{experiment.symbolsStreamed.toLocaleString()}</strong></span>
            <span><small>Sample</small><strong>{experiment.boundedSample ? "Bounded smoke test" : "Full current-survivor diagnostic"}</strong></span>
            <span title={experiment.artifactSha256}><small>Artifact</small><strong>{experiment.artifactSha256.slice(0, 12)}…</strong></span>
          </div>
          <div className="model-audit__tabs" role="tablist" aria-label="Prediction horizon">
            {horizons.map((item) => (
              <button aria-selected={item.horizonSessions === horizon?.horizonSessions} key={item.horizonSessions} onClick={() => setSelected(item.horizonSessions)} role="tab" type="button">
                {item.horizonSessions} sessions
              </button>
            ))}
          </div>
          {horizon && <HoldoutStory horizon={horizon} />}
          <p className="model-audit__method">{board.data.methodology}</p>
        </>
      )}
    </section>
  );
}
