import { researchDeployment } from "../../app/deployment";
import type {
  AutomationPolicy,
  InvestmentMandate,
  InvestmentOperatingView,
  ResearchRun,
  ResearchStrategy,
  ShadowPortfolio,
  StrategyDataReadiness,
} from "../../app/api-client";

function sessionDate(daysAgo: number): string {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - daysAgo);
  return date.toISOString().slice(0, 10);
}

const isDse = researchDeployment.market === "DSE";
const primaryCode = isDse ? "BRACBANK" : "NXTC";
const secondaryCode = isDse ? "BXPHARMA" : "AEON";
const strategyKey = isDse ? "dse_reversal_v1" : "us_breakout_v1";
const initialCapital = isDse ? 10_000_000 : 100_000;
const primaryShares = isDse ? 7300 : 1180;
const primaryFillPrice = isDse ? 142.4 : 8.42;
const primaryGrossValue = primaryShares * primaryFillPrice;

export const previewStrategies: ResearchStrategy[] = isDse
  ? [
      {
        key: "dse_reversal_v1",
        market: "DSE",
        name: "DSE liquid reversal",
        family: "reversal",
        horizon: "eod_swing",
        selectionKey: "top_ranked",
        sizingKey: "inverse_volatility",
        methodologyVersion: "dse-liquid-reversal-v1",
        minimumLookback: 126,
        rebalanceSessions: 5,
        maximumPositions: 8,
        requiredEvidence: [],
        researchState: "diagnostic",
        automationEligible: true,
        description: "Liquid drawdown recoveries with participation confirmation.",
      },
    ]
  : [
      {
        key: "us_breakout_v1",
        market: "US",
        name: "US liquid trend participation",
        family: "trend",
        horizon: "eod_swing",
        selectionKey: "top_ranked",
        sizingKey: "inverse_volatility",
        methodologyVersion: "us-liquid-trend-v1",
        minimumLookback: 200,
        rebalanceSessions: 5,
        maximumPositions: 10,
        requiredEvidence: [],
        researchState: "diagnostic",
        automationEligible: true,
        description: "Liquid positive trends with participation and extension control.",
      },
      {
        key: "us_leader_capture_v1",
        market: "US",
        name: "US leader capture",
        family: "leader_capture",
        horizon: "multi_month",
        selectionKey: "rank_buffer_2x",
        sizingKey: "equal_weight_full_gross",
        methodologyVersion: "us-leader-capture-v1",
        minimumLookback: 252,
        rebalanceSessions: 20,
        maximumPositions: 10,
        requiredEvidence: [
          "revenue_growth_yoy_pct",
          "revenue_acceleration_pct",
          "reported_earnings_confirmation",
        ],
        researchState: "candidate",
        automationEligible: false,
        description: "Persistent price leadership confirmed by point-in-time SEC acceleration.",
      },
    ];

export const previewStrategyDataReadiness: StrategyDataReadiness = {
  workspaceId: "00000000-0000-0000-0000-000000000001",
  tenantId: "bullsofdhaka",
  market: "DSE",
  strategyKey: "dse_trend_pullback_intraday_v1",
  state: "data_blocked",
  barKind: "sampled_delayed_quote",
  timeQuality: "ingestion_upper_bound",
  capturedSessions: 3,
  completeSessions: 2,
  eligibleCaptureSessions: 2,
  requiredCompleteSessions: 60,
  observationCount: 23_640,
  barCount: 23_640,
  firstSession: sessionDate(4),
  latestSession: sessionDate(0),
  historicalDiagnosticEligible: false,
  blockers: [
    "Only 2 complete intraday sessions are retained; the preregistration floor is 60.",
    "Inactive and delisted DSE history is not yet complete.",
    "The intraday trend-pullback experiment specification has not been frozen.",
  ],
  latestQuality: {
    sessionDate: sessionDate(0),
    status: "complete",
    observedSlots: 20,
    expectedSlots: 20,
    observedSymbols: 394,
    expectedSymbols: 396,
    slotCompletenessPct: 100,
    symbolCompletenessPct: 99.495,
    vwapCoveragePct: 98.7,
    counterRegressions: 0,
    latestObservedAt: new Date().toISOString(),
    captureAgeMinutes: 18,
    researchEligible: true,
    blockers: [],
  },
};

export const previewInvestmentMandate: InvestmentMandate = {
  id: "00000000-0000-0000-0000-000000000601",
  workspaceId: "00000000-0000-0000-0000-000000000001",
  tenantId: researchDeployment.tenant,
  market: researchDeployment.market,
  version: 1,
  status: "active",
  objective: "Capital preservation and benchmark-relative compounding through registered long-only strategies.",
  benchmarkKey: isDse ? "dsex_equal_weight_proxy" : "us_equal_weight_proxy",
  maxGrossExposurePct: isDse ? 85 : 90,
  minCashReservePct: isDse ? 15 : 10,
  maxPositionWeightPct: isDse ? 12 : 10,
  maxSectorWeightPct: isDse ? 30 : 25,
  maxAdvParticipationPct: isDse ? 2 : 5,
  portfolioDrawdownBrakePct: isDse ? 15 : 18,
  stressLossLimitPct: isDse ? 12 : 15,
  specificationHash: "0".repeat(64),
  effectiveAt: new Date().toISOString(),
  supersededAt: null,
};

export const previewShadowPortfolios: ShadowPortfolio[] = [
  {
    id: "00000000-0000-0000-0000-000000000101",
    workspaceId: "00000000-0000-0000-0000-000000000001",
    tenantId: researchDeployment.tenant,
    market: researchDeployment.market,
    sourceRunId: "00000000-0000-0000-0000-000000000201",
    name: isDse ? "DSE Drawdown Recovery (Diagnostic)" : "US Trend Participation (Diagnostic)",
    strategyKey,
    status: "active",
    initialCapital,
    inceptionDate: sessionDate(5),
    lastEvaluatedOn: sessionDate(0),
    configuration: {
      observable_universe: [primaryCode, secondaryCode],
      promotion: {
        status: "diagnostic",
        headline: "Historical data gates block promotion while forward evidence collects.",
        checks: [
          { key: "historical_validation", passed: false },
          { key: "forward_sessions", passed: false },
          { key: "maximum_drawdown", passed: true },
        ],
      },
    },
    snapshots: [
      {
        id: "00000000-0000-0000-0000-000000000301",
        asOfDate: sessionDate(4),
        sessionNumber: 1,
        nav: initialCapital,
        cash: initialCapital,
        benchmarkNav: initialCapital,
        peakNav: initialCapital,
        grossExposurePct: 0,
        drawdownPct: 0,
        cumulativeFees: 0,
        cumulativeTurnover: 0,
        positions: {},
        targetWeights: { [primaryCode]: 0.1 },
        trades: [],
        pendingSettlements: [],
        riskInterventions: [],
      },
      {
        id: "00000000-0000-0000-0000-000000000302",
        asOfDate: sessionDate(0),
        sessionNumber: 2,
        nav: initialCapital * 1.006,
        cash: initialCapital * 0.89,
        benchmarkNav: initialCapital * 1.003,
        peakNav: initialCapital * 1.009,
        grossExposurePct: 11,
        drawdownPct: 0.3,
        cumulativeFees: initialCapital * 0.0004,
        cumulativeTurnover: 10.8,
        positions: { [primaryCode]: { shares: primaryShares, average_cost: primaryFillPrice } },
        targetWeights: { [primaryCode]: 0.1, [secondaryCode]: 0.08 },
        trades: [
          {
            date: sessionDate(0),
            session_number: 2,
            code: primaryCode,
            side: "buy",
            quantity: primaryShares,
            fill_price: primaryFillPrice,
            gross_value: primaryGrossValue,
            fee: initialCapital * 0.0004,
            reason: "prior-close shadow target",
          },
        ],
        pendingSettlements: [],
        riskInterventions: [
          {
            rule: "cash_constraint",
            code: secondaryCode,
            detail: "The desired target was reduced to preserve the configured cash and gross-exposure limits.",
          },
        ],
      },
    ],
  },
];

export const previewAutomationPolicy: AutomationPolicy = {
  id: "00000000-0000-0000-0000-000000000401",
  workspaceId: "00000000-0000-0000-0000-000000000001",
  tenantId: researchDeployment.tenant,
  market: researchDeployment.market,
  enabled: true,
  queueLimit: 20,
  researchLimit: 5,
  capTier: null,
  strategyKey,
  universeLimit: 25,
  initialCapital,
  nextRunAt: new Date(Date.now() + 3 * 60 * 60 * 1000).toISOString(),
  lastStartedAt: new Date(Date.now() - 35 * 60 * 1000).toISOString(),
  lastCompletedAt: new Date(Date.now() - 28 * 60 * 1000).toISOString(),
  lastRunStatus: "succeeded",
  lastError: null,
};

export const previewResearchRuns: ResearchRun[] = [
  {
    id: "00000000-0000-0000-0000-000000000501",
    workspaceId: "00000000-0000-0000-0000-000000000001",
    tenantId: researchDeployment.tenant,
    market: researchDeployment.market,
    runKind: "lifecycle",
    status: "succeeded",
    question: "Run the bounded post-close investment research lifecycle.",
    code: null,
    parameters: {},
    knowledgeCutoffAt: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
    provider: null,
    model: null,
    codeVersion: "preview",
    evidenceSnapshotHash: "preview-evidence-snapshot",
    requestedAt: new Date(Date.now() - 35 * 60 * 1000).toISOString(),
    completedAt: new Date(Date.now() - 28 * 60 * 1000).toISOString(),
    claims: [],
    steps: [
      {
        ordinal: 1,
        kind: "evidence_changed_research",
        status: "succeeded",
        output: {
          companies: [
            { ticker: primaryCode, status: "monitor", action: "researched" },
            { ticker: secondaryCode, status: "qualified", action: "researched" },
          ],
        },
        metrics: {},
      },
      {
        ordinal: 2,
        kind: "forward_shadow_reconciliation",
        status: "succeeded",
        output: {
          sessions_advanced: 1,
          new_executions: previewShadowPortfolios[0]!.snapshots[1]!.trades,
          target_changes: [
            {
              code: secondaryCode,
              previous_weight: 0,
              target_weight: 0.08,
              action: "entry_target",
              date: sessionDate(0),
              session_number: 2,
            },
          ],
          new_risk_interventions: previewShadowPortfolios[0]!.snapshots[1]!.riskInterventions,
        },
        metrics: {},
      },
      {
        ordinal: 3,
        kind: "outcome_calibration",
        status: "succeeded",
        output: { newly_matured: 0 },
        metrics: {},
      },
    ],
  },
];

export const previewInvestmentOperatingView: InvestmentOperatingView = {
  workspaceId: "00000000-0000-0000-0000-000000000001",
  tenantId: researchDeployment.tenant,
  market: researchDeployment.market,
  generatedAt: new Date().toISOString(),
  mandate: previewInvestmentMandate,
  trials: [
    {
      id: "00000000-0000-0000-0000-000000000701",
      sourceRunId: previewShadowPortfolios[0]!.sourceRunId,
      workspaceId: "00000000-0000-0000-0000-000000000001",
      tenantId: researchDeployment.tenant,
      market: researchDeployment.market,
      strategyKey,
      strategyVersion: isDse ? "dse-liquid-reversal-v1" : "us-liquid-trend-v1",
      status: "shadow",
      registrationState: "preregistered",
      trialSequence: 1,
      multipleTestingPolicy: "family_gate_v1",
      economicHypothesis: isDse
        ? "Forced selling exhaustion may create a liquid, controlled mean-reversion opportunity."
        : "Slow institutional adjustment may sustain a liquid, participation-confirmed trend.",
      specification: { execution: { earliest_fill: "next observable session open" } },
      specificationHash: "1".repeat(64),
      outcome: { validation_status: "diagnostic" },
      registeredAt: new Date(Date.now() - 7 * 86_400_000).toISOString(),
      completedAt: new Date(Date.now() - 7 * 86_400_000 + 10_000).toISOString(),
    },
  ],
  portfolios: [
    {
      portfolioId: previewShadowPortfolios[0]!.id,
      asOfDate: sessionDate(0),
      mandate: previewInvestmentMandate,
      mandateVersion: 1,
      mandateBinding: "pinned",
      risk: {
        grossExposurePct: 11,
        cashReservePct: 89,
        largestPositionPct: isDse ? 10.4 : 9.9,
        largestSectorPct: isDse ? 10.4 : 9.9,
        concentrationHhi: 1,
        effectivePositions: 1,
        weightedAverageCorrelation: null,
        maximumPairCorrelation: null,
        maximumExitDays: 0.4,
        limitChecks: [
          { key: "gross_exposure", status: "within_limit", actual: 11, limit: isDse ? 85 : 90, unit: "pct", detail: "Total invested weight versus the mandate ceiling." },
          { key: "single_name", status: "within_limit", actual: 10.4, limit: isDse ? 12 : 10, unit: "pct", detail: "Largest observable security weight." },
        ],
        stressScenarios: [
          { key: "broad_market_down_10", label: "Broad market -10%", shockPct: -10, estimatedLossPct: 1.1, status: "within_limit", methodology: "Applies the shock to current gross exposure." },
        ],
        breachedLimits: [],
        unavailableLimits: [],
        dataComplete: true,
        dataQualityNotes: ["At least 20 aligned return observations are required for correlation diagnostics."],
      },
      attribution: {
        portfolioReturnPct: 0.6,
        benchmarkReturnPct: 0.3,
        excessReturnPct: 0.3,
        components: [
          { key: "market_beta", label: "Market beta proxy", contributionPct: 0, quality: "proxy", explanation: "Prior-close exposure multiplied by benchmark return." },
          { key: "active_residual", label: "Active strategy residual", contributionPct: 0.64, quality: "proxy", explanation: "Still combines selection, sizing, and timing." },
          { key: "costs", label: "Explicit fees", contributionPct: -0.04, quality: "exact", explanation: "Recorded paper fees." },
          { key: "linking_residual", label: "Compounding residual", contributionPct: 0, quality: "exact", explanation: "Reconciles daily attribution to compounded return." },
          { key: "timing", label: "Execution timing", contributionPct: null, quality: "unavailable", explanation: "Arrival-price history is not retained." },
        ],
        rejectedActions: 1,
        methodologyVersion: "atlas-additive-attribution-v1",
      },
      recentEvents: [],
    },
  ],
};
