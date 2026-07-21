import type { ResearchRun, ResearchRunStep, ShadowPortfolio } from "../../app/api-client";

export interface ShadowExecution {
  id: string;
  sessionNumber: number;
  date: string;
  code: string;
  side: "buy" | "sell";
  quantity: number;
  fillPrice: number;
  grossValue: number;
  fee: number;
  cashImpact: number;
  reason: string;
}

export interface LifecycleRunDelta {
  researchChanges: Array<{
    ticker: string;
    status: string;
    action: "researched" | "unchanged" | "skipped";
  }>;
  sessionsAdvanced: number;
  executions: ShadowExecution[];
  targetChanges: Array<{
    code: string;
    previousWeight: number;
    targetWeight: number;
    action: "entry_target" | "exit_target" | "increase_target" | "reduce_target";
    date: string;
    sessionNumber: number;
  }>;
  riskInterventions: number;
  calibrationMatured: number;
}

export interface AutonomousDecision {
  status: "qualified" | "monitor" | "rejected" | "abstained";
  confidence: number;
  evidenceCompletenessPct: number;
  thesisStrength: "weak" | "mixed" | "moderate" | "strong" | "unrated";
  outcomeCalibration: "uncalibrated";
  headline: string;
  thesis: string;
  counterThesis: string;
  invalidationRules: string[];
  missingEvidence: string[];
  limitations: string[];
  strategyKey: string | null;
  lenses: Array<{
    key: string;
    label: string;
    assessment: "constructive" | "balanced" | "caution" | "unknown";
    summary: string;
    factKeys: string[];
  }>;
  scenarios: Array<{
    key: "base" | "upside" | "downside";
    title: string;
    state: "current" | "conditional";
    condition: string;
    implication: string;
    watchItems: string[];
  }>;
  nextEvidence: Array<{
    priority: "high" | "medium" | "routine";
    question: string;
    reason: string;
  }>;
}

export interface BacktestMetric {
  label: "full" | "train" | "validation" | "test";
  sessions: number;
  totalReturnPct: number | null;
  annualizedReturnPct: number | null;
  annualizedVolatilityPct: number | null;
  sharpe: number | null;
  sortino: number | null;
  maxDrawdownPct: number | null;
}

export interface DeflatedSharpe {
  /** Probability the edge is real after adjusting for how many variants were tried. */
  deflatedSharpe: number;
  /** The same confidence before any multiple-testing adjustment. */
  probabilisticSharpe: number;
  /** Sharpe the best of N worthless strategies would be expected to show by luck. */
  benchmarkSharpe: number;
  numTrials: number;
  threshold: number;
  passes: boolean;
}

export interface CostStressTier {
  label: string;
  oneWayBps: number;
  measured: boolean;
  netReturnPct: number;
  excessReturnPct: number;
  edgeSurvives: boolean;
}

export interface CostStress {
  tiers: CostStressTier[];
  /** Lowest one-way cost at which the edge stops beating its benchmark. */
  edgeDiesAtBps: number | null;
  measuredCoverage: number;
  universeSize: number;
}

export interface BacktestResult {
  engineVersion: string;
  strategy: {
    key: string;
    name: string;
    description: string;
    rebalanceSessions: number;
    maximumPositions: number;
  };
  riskPolicy: Record<string, number | string>;
  startDate: string | null;
  endDate: string | null;
  initialCapital: number;
  finalNav: number;
  benchmarkFinal: number;
  trades: Array<Record<string, unknown>>;
  equityCurve: Array<{
    date: string;
    nav: number;
    benchmark: number;
    cash: number;
    grossExposurePct: number;
    drawdownPct: number;
  }>;
  riskInterventions: Array<Record<string, unknown>>;
  metrics: BacktestMetric[];
  turnoverPct: number;
  feesPaid: number;
  validationStatus: "diagnostic" | "eligible_for_shadow";
  failedGates: string[];
  warnings: string[];
  // Overfitting guard (institutional study 13.3.3) and cost-stress tiers (13.2). Both are
  // absent on runs recorded before those gates existed, so both are nullable.
  deflatedSharpe: DeflatedSharpe | null;
  costStress: CostStress | null;
  latestTargetWeights: Record<string, number>;
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function text(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function numeric(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function nullableNumeric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function execution(
  raw: unknown,
  options: { id: string; fallbackDate: string; fallbackSession: number },
): ShadowExecution | null {
  const { id, fallbackDate, fallbackSession } = options;
  const trade = record(raw);
  const date = text(trade?.date, fallbackDate);
  const code = text(trade?.code).toUpperCase();
  const side = text(trade?.side);
  const quantity = numeric(trade?.quantity, Number.NaN);
  const fillPrice = numeric(trade?.fill_price, Number.NaN);
  const grossValue = numeric(trade?.gross_value, Number.NaN);
  const fee = numeric(trade?.fee, Number.NaN);
  if (
    !trade ||
    !/^\d{4}-\d{2}-\d{2}$/.test(date) ||
    !code ||
    (side !== "buy" && side !== "sell") ||
    !Number.isFinite(quantity) || quantity <= 0 ||
    !Number.isFinite(fillPrice) || fillPrice <= 0 ||
    !Number.isFinite(grossValue) || grossValue <= 0 ||
    !Number.isFinite(fee) || fee < 0
  ) return null;
  return {
    id,
    sessionNumber: numeric(trade.session_number, fallbackSession),
    date,
    code,
    side,
    quantity,
    fillPrice,
    grossValue,
    fee,
    cashImpact: side === "buy" ? -(grossValue + fee) : grossValue - fee,
    reason: text(trade.reason, "Systematic target rebalance"),
  };
}

export function shadowExecutions(portfolio: ShadowPortfolio | undefined): ShadowExecution[] {
  if (!portfolio) return [];

  return portfolio.snapshots
    .flatMap((snapshot) => snapshot.trades.flatMap((raw, index) => {
      const parsed = execution(raw, {
        id: `${snapshot.id}:${index}`,
        fallbackDate: snapshot.asOfDate,
        fallbackSession: snapshot.sessionNumber,
      });
      return parsed ? [parsed] : [];
    }))
    .sort((left, right) =>
      right.date.localeCompare(left.date) ||
      right.sessionNumber - left.sessionNumber ||
      left.code.localeCompare(right.code),
    );
}

export function lifecycleRunDelta(run: ResearchRun | undefined): LifecycleRunDelta {
  const research = run?.steps.find((step) => step.kind === "evidence_changed_research")?.output;
  const shadow = run?.steps.find((step) => step.kind === "forward_shadow_reconciliation")?.output;
  const calibration = run?.steps.find((step) => step.kind === "outcome_calibration")?.output;
  const researchChanges = Array.isArray(research?.companies)
    ? research.companies.flatMap((raw) => {
        const item = record(raw);
        const action = text(item?.action);
        const ticker = text(item?.ticker).toUpperCase();
        if (!item || !ticker || !["researched", "unchanged", "skipped"].includes(action)) return [];
        return [{
          ticker,
          status: text(item.status, "unknown"),
          action: action as LifecycleRunDelta["researchChanges"][number]["action"],
        }];
      })
    : [];
  const executions = Array.isArray(shadow?.new_executions)
    ? shadow.new_executions.flatMap((raw, index) => {
        const parsed = execution(raw, {
          id: `${run?.id ?? "run"}:execution:${index}`,
          fallbackDate: "",
          fallbackSession: 0,
        });
        return parsed ? [parsed] : [];
      })
    : [];
  const validTargetActions = [
    "entry_target",
    "exit_target",
    "increase_target",
    "reduce_target",
  ];
  const targetChanges = Array.isArray(shadow?.target_changes)
    ? shadow.target_changes.flatMap((raw) => {
        const item = record(raw);
        const action = text(item?.action);
        const code = text(item?.code).toUpperCase();
        if (!item || !code || !validTargetActions.includes(action)) return [];
        return [{
          code,
          previousWeight: numeric(item.previous_weight),
          targetWeight: numeric(item.target_weight),
          action: action as LifecycleRunDelta["targetChanges"][number]["action"],
          date: text(item.date),
          sessionNumber: numeric(item.session_number),
        }];
      })
    : [];
  return {
    researchChanges,
    sessionsAdvanced: numeric(shadow?.sessions_advanced),
    executions,
    targetChanges,
    riskInterventions: Array.isArray(shadow?.new_risk_interventions)
      ? shadow.new_risk_interventions.length
      : 0,
    calibrationMatured: numeric(calibration?.newly_matured),
  };
}

function financialLenses(value: unknown): AutonomousDecision["lenses"] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((raw) => {
    const item = record(raw);
    const assessment = text(item?.assessment);
    if (
      !item ||
      !["constructive", "balanced", "caution", "unknown"].includes(assessment)
    ) return [];
    return [{
      key: text(item.key),
      label: text(item.label, "Research lens"),
      assessment: assessment as AutonomousDecision["lenses"][number]["assessment"],
      summary: text(item.summary),
      factKeys: strings(item.fact_keys),
    }];
  });
}

function financialScenarios(value: unknown): AutonomousDecision["scenarios"] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((raw) => {
    const item = record(raw);
    const key = text(item?.key);
    const state = text(item?.state);
    if (!item || !["base", "upside", "downside"].includes(key) || !["current", "conditional"].includes(state)) return [];
    return [{
      key: key as AutonomousDecision["scenarios"][number]["key"],
      title: text(item.title, "Scenario"),
      state: state as AutonomousDecision["scenarios"][number]["state"],
      condition: text(item.condition),
      implication: text(item.implication),
      watchItems: strings(item.watch_items),
    }];
  });
}

function evidenceRequests(value: unknown): AutonomousDecision["nextEvidence"] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((raw) => {
    const item = record(raw);
    const priority = text(item?.priority);
    if (!item || !["high", "medium", "routine"].includes(priority)) return [];
    return [{
      priority: priority as AutonomousDecision["nextEvidence"][number]["priority"],
      question: text(item.question),
      reason: text(item.reason),
    }];
  });
}

export function autonomousDecision(run: ResearchRun | undefined): AutonomousDecision | null {
  const decision = record(run?.parameters.decision);
  if (!decision) return null;
  const status = text(decision.status);
  if (!["qualified", "monitor", "rejected", "abstained"].includes(status)) return null;
  const thesisStrength = text(decision.thesis_strength);
  return {
    status: status as AutonomousDecision["status"],
    confidence: numeric(decision.confidence),
    evidenceCompletenessPct: numeric(decision.evidence_completeness_pct),
    thesisStrength: ["weak", "mixed", "moderate", "strong"].includes(thesisStrength)
      ? thesisStrength as AutonomousDecision["thesisStrength"]
      : "unrated",
    outcomeCalibration: "uncalibrated",
    headline: text(decision.headline, "Autonomous review completed"),
    thesis: text(decision.thesis, "No supported thesis was produced."),
    counterThesis: text(decision.counter_thesis, "No counter-thesis was produced."),
    invalidationRules: strings(decision.invalidation_rules),
    missingEvidence: strings(decision.missing_evidence),
    limitations: strings(decision.limitations),
    strategyKey: typeof decision.strategy_key === "string" ? decision.strategy_key : null,
    lenses: financialLenses(decision.lenses),
    scenarios: financialScenarios(decision.scenarios),
    nextEvidence: evidenceRequests(decision.next_evidence),
  };
}

function backtestStep(run: ResearchRun | undefined): ResearchRunStep | undefined {
  return run?.steps.find((step) => step.kind === "portfolio_backtest");
}

function deflatedSharpe(run: ResearchRun | undefined): DeflatedSharpe | null {
  const gate = run?.steps.find((step) => step.kind === "validation_gate");
  const payload = record(record(gate?.output)?.deflated_sharpe);
  if (!payload) return null;
  const value = numeric(payload.deflated_sharpe);
  if (!Number.isFinite(value)) return null;
  return {
    deflatedSharpe: value,
    probabilisticSharpe: numeric(payload.probabilistic_sharpe),
    benchmarkSharpe: numeric(payload.benchmark_sharpe),
    numTrials: numeric(payload.num_trials),
    threshold: numeric(payload.threshold),
    passes: payload.passes === true,
  };
}

function costStress(run: ResearchRun | undefined): CostStress | null {
  const step = run?.steps.find((item) => item.kind === "cost_stress");
  const payload = record(step?.output);
  if (!payload || !Array.isArray(payload.outcomes)) return null;
  const tiers = payload.outcomes
    .map((entry) => {
      const outcome = record(entry);
      const tier = record(outcome?.tier);
      if (!outcome || !tier) return null;
      return {
        label: text(tier.label) ?? "",
        oneWayBps: numeric(tier.one_way_bps),
        measured: tier.measured === true,
        netReturnPct: numeric(outcome.net_return_pct),
        excessReturnPct: numeric(outcome.excess_return_pct),
        edgeSurvives: outcome.edge_survives === true,
      };
    })
    .filter((tier): tier is CostStressTier => tier !== null);
  if (tiers.length === 0) return null;
  const dies = payload.edge_dies_at_bps;
  return {
    tiers,
    edgeDiesAtBps: typeof dies === "number" ? dies : null,
    measuredCoverage: numeric(payload.measured_coverage),
    universeSize: numeric(payload.universe_size),
  };
}

export function backtestResult(run: ResearchRun | undefined): BacktestResult | null {
  const output = record(backtestStep(run)?.output);
  const strategy = record(output?.strategy);
  const policy = record(output?.risk_policy);
  if (!output || !strategy || !policy) return null;
  const validationStatus = text(output.validation_status);
  if (validationStatus !== "diagnostic" && validationStatus !== "eligible_for_shadow") return null;
  const metrics = Array.isArray(output.metrics)
    ? output.metrics.flatMap((raw) => {
        const item = record(raw);
        const label = text(item?.label);
        if (!item || !["full", "train", "validation", "test"].includes(label)) return [];
        return [{
          label: label as BacktestMetric["label"],
          sessions: numeric(item.sessions),
          totalReturnPct: nullableNumeric(item.total_return_pct),
          annualizedReturnPct: nullableNumeric(item.annualized_return_pct),
          annualizedVolatilityPct: nullableNumeric(item.annualized_volatility_pct),
          sharpe: nullableNumeric(item.sharpe),
          sortino: nullableNumeric(item.sortino),
          maxDrawdownPct: nullableNumeric(item.max_drawdown_pct),
        }];
      })
    : [];
  const equityCurve = Array.isArray(output.equity_curve)
    ? output.equity_curve.flatMap((raw) => {
        const item = record(raw);
        if (!item || typeof item.date !== "string") return [];
        return [{
          date: item.date,
          nav: numeric(item.nav),
          benchmark: numeric(item.benchmark),
          cash: numeric(item.cash),
          grossExposurePct: numeric(item.gross_exposure_pct),
          drawdownPct: numeric(item.drawdown_pct),
        }];
      })
    : [];
  return {
    engineVersion: text(output.engine_version),
    strategy: {
      key: text(strategy.key),
      name: text(strategy.name),
      description: text(strategy.description),
      rebalanceSessions: numeric(strategy.rebalance_sessions),
      maximumPositions: numeric(strategy.maximum_positions),
    },
    riskPolicy: Object.fromEntries(
      Object.entries(policy).filter((entry): entry is [string, number | string] =>
        typeof entry[1] === "number" || typeof entry[1] === "string",
      ),
    ),
    startDate: typeof output.start_date === "string" ? output.start_date : null,
    endDate: typeof output.end_date === "string" ? output.end_date : null,
    initialCapital: numeric(output.initial_capital),
    finalNav: numeric(output.final_nav),
    benchmarkFinal: numeric(output.benchmark_final),
    trades: Array.isArray(output.trades) ? output.trades.filter((item) => record(item) !== null) as Array<Record<string, unknown>> : [],
    equityCurve,
    riskInterventions: Array.isArray(output.risk_interventions) ? output.risk_interventions.filter((item) => record(item) !== null) as Array<Record<string, unknown>> : [],
    metrics,
    turnoverPct: numeric(output.turnover_pct),
    feesPaid: numeric(output.fees_paid),
    validationStatus,
    failedGates: strings(output.failed_gates),
    warnings: strings(output.warnings),
    deflatedSharpe: deflatedSharpe(run),
    costStress: costStress(run),
    latestTargetWeights: Object.fromEntries(
      Object.entries(record(output.latest_target_weights) ?? {}).filter(
        (entry): entry is [string, number] => typeof entry[1] === "number",
      ),
    ),
  };
}
